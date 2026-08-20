import shutil
import tempfile
from unittest import mock

from django.test import TestCase, override_settings

from . import templates_repo
from .models import Generation
from .services import copywriter, generator, prompt_builder, zone_prompt
from .services.brief import brief_as_text, build_brief

VALID_ANSWERS = {
    'event_type': 'product_presentation',
    'goals': ['sales', 'press'],
    'emotion': 'pride',
    'brand_attributes': ['premium', 'modern', 'bold'],
    'reference': 'apple',
    'scale': 'national',
}

MEDIA = tempfile.mkdtemp(prefix='eventm-test-')


class TemplateRepoTests(TestCase):
    def test_lists_templates_grouped_by_number(self):
        listed = templates_repo.list_templates()
        self.assertEqual(
            [t['id'] for t in listed],
            ['template-1', 'template-2', 'template-3'],
        )
        self.assertTrue(all(t['pages'] == 2 for t in listed))

    def test_load_pages_returns_ordered_slides(self):
        pages = templates_repo.load_pages('template-1')
        self.assertEqual([page for page, _ in pages], [1, 2])
        self.assertIn('elements', pages[0][1])

    def test_load_pages_returns_copies(self):
        first = templates_repo.load_pages('template-1')[0][1]
        first['elements'][0]['content'] = 'mutated'
        second = templates_repo.load_pages('template-1')[0][1]
        self.assertNotEqual(second['elements'][0]['content'], 'mutated')

    def test_unknown_template_raises(self):
        with self.assertRaises(templates_repo.TemplateNotFound):
            templates_repo.load_pages('template-999')
        self.assertFalse(templates_repo.template_exists('nope'))


class PromptBuilderTests(TestCase):
    def test_position_maps_to_spatial_language(self):
        described = prompt_builder.describe_position(
            {'x': 4, 'y': 8, 'width': 45, 'height': 12}
        )
        self.assertIn('top left', described)
        self.assertIn('45%', described)

    def test_centre_position_is_not_doubled_up(self):
        described = prompt_builder.describe_position(
            {'x': 40, 'y': 40, 'width': 20, 'height': 20}
        )
        self.assertIn('dead centre', described)

    def test_typography_vocabulary_is_translated(self):
        described = prompt_builder.describe_typography(
            {'size': 'xlarge', 'weight': 'bold', 'style': 'serif',
             'letter_spacing': 'wide'}
        )
        self.assertIn('very large bold serif', described)
        self.assertIn('wide letter spacing', described)

    def test_prompt_covers_every_element_of_every_template(self):
        brief = brief_as_text(build_brief(VALID_ANSWERS))
        for template in templates_repo.list_templates():
            for page, slide in templates_repo.load_pages(template['id']):
                prompt = prompt_builder.build_image_prompt(slide, brief, page, 2)

                # Every element gets its own numbered entry, and its content
                # (text or artwork description) survives into the prompt.
                for index, element in enumerate(slide['elements'], start=1):
                    self.assertIn(f'{index}. ', prompt)
                    self.assertIn(element['content'].strip()[:40], prompt)

                # No raw template vocabulary leaks through untranslated.
                for token in ('xlarge', 'xsmall', 'extrabold', 'italic_serif',
                              'rectangle_full_bleed', 'accent_bright'):
                    self.assertNotIn(token, prompt, f'{token} in {template["id"]}')

    def test_text_elements_are_quoted_verbatim(self):
        slide = {
            'elements': [
                {'id': 'el_1', 'type': 'title', 'content': 'Запуск',
                 'position': {'x': 0, 'y': 0, 'width': 50, 'height': 10}},
            ]
        }
        prompt = prompt_builder.build_image_prompt(slide, 'brief', 1, 2)
        self.assertIn('"Запуск"', prompt)

    def test_inset_pulls_an_edge_hugging_box_into_the_safe_area(self):
        inset = prompt_builder.inset_position(
            {'x': 2, 'y': 0, 'width': 48, 'height': 100}
        )
        self.assertGreaterEqual(inset['x'], prompt_builder.SAFE_MARGIN)
        self.assertGreaterEqual(inset['y'], prompt_builder.SAFE_MARGIN)
        self.assertLessEqual(
            inset['y'] + inset['height'],
            prompt_builder.CANVAS - prompt_builder.SAFE_MARGIN + 0.01,
        )

    def test_inset_preserves_relative_order_of_elements(self):
        left = prompt_builder.inset_position({'x': 4, 'y': 10, 'width': 20})
        right = prompt_builder.inset_position({'x': 60, 'y': 10, 'width': 20})
        self.assertLess(left['x'], right['x'])

    def test_text_position_states_explicit_offsets(self):
        described = prompt_builder.describe_position({'x': 8, 'y': 32,
                                                      'width': 42, 'height': 35})
        self.assertIn('left edge beginning 8% in from the slide border',
                      described)

    def test_pictorial_elements_keep_their_raw_coordinates(self):
        element = {'id': 'el_1', 'type': 'image', 'content': 'a crowd',
                   'position': {'x': 0, 'y': 0, 'width': 50, 'height': 100}}
        described = prompt_builder.describe_element(1, element)
        self.assertNotIn('left edge beginning', described)

    def test_every_text_box_in_every_template_lands_inside_the_safe_area(self):
        margin = prompt_builder.SAFE_MARGIN
        for template in templates_repo.list_templates():
            for _, slide in templates_repo.load_pages(template['id']):
                for element in slide['elements']:
                    if element['type'] in prompt_builder.PICTORIAL_TYPES:
                        continue
                    inset = prompt_builder.inset_position(element['position'])
                    self.assertGreaterEqual(inset['x'], margin - 0.01)
                    self.assertLessEqual(
                        inset['x'] + inset['width'],
                        prompt_builder.CANVAS - margin + 0.01,
                        f'{template["id"]} {element["id"]}',
                    )

    def test_edge_hugs_reports_every_offending_side(self):
        self.assertEqual(
            prompt_builder.edge_hugs({'x': 1, 'y': 1, 'width': 98, 'height': 98}),
            ['left', 'top', 'right', 'bottom'],
        )
        self.assertEqual(
            prompt_builder.edge_hugs({'x': 20, 'y': 20,
                                      'width': 40, 'height': 40}),
            [],
        )

    def test_every_template_text_block_stays_inside_the_safe_area(self):
        brief = brief_as_text(build_brief(VALID_ANSWERS))
        for template in templates_repo.list_templates():
            for page, slide in templates_repo.load_pages(template['id']):
                prompt = prompt_builder.build_image_prompt(slide, brief, page, 2)
                self.assertIn('SAFE AREA', prompt)
                self.assertIn('Cyrillic', prompt)

    def test_pictorial_elements_are_described_not_quoted(self):
        slide = {
            'elements': [
                {'id': 'el_1', 'type': 'image', 'content': 'a crowd',
                 'position': {'x': 50, 'y': 0, 'width': 50, 'height': 100}},
            ]
        }
        prompt = prompt_builder.build_image_prompt(slide, 'brief', 1, 2)
        self.assertIn('Depicts: a crowd', prompt)
        self.assertNotIn('"a crowd"', prompt)


class ZonePromptTests(TestCase):
    def test_zones_match_each_template_layout_description(self):
        """The layout description names the zones; the split must agree."""
        expected = {
            ('template-1', 1): {'LEFT SIDE', 'CENTRE', 'RIGHT SIDE', 'BOTTOM'},
            ('template-1', 2): {'TOP', 'LEFT SIDE', 'CENTRE', 'RIGHT SIDE',
                                'BOTTOM'},
            ('template-2', 1): {'CENTRE'},
            ('template-2', 2): {'LEFT SIDE', 'RIGHT SIDE'},
            ('template-3', 1): {'LEFT SIDE', 'RIGHT SIDE'},
            ('template-3', 2): {'TOP', 'LEFT SIDE', 'RIGHT SIDE'},
        }
        for template in templates_repo.list_templates():
            for page, slide in templates_repo.load_pages(template['id']):
                zones = set(zone_prompt.group_by_zone(slide['elements']))
                self.assertEqual(
                    zones, expected[(template['id'], page)],
                    f'{template["id"]} page {page}',
                )

    def test_left_column_heading_is_not_mistaken_for_a_top_band(self):
        """A wide heading with a photo beside it belongs to its column."""
        heading = {'id': 'el_1', 'type': 'title',
                   'position': {'x': 3, 'y': 5, 'width': 55, 'height': 22}}
        photo = {'id': 'el_2', 'type': 'image',
                 'position': {'x': 58, 'y': 0, 'width': 42, 'height': 100}}
        self.assertEqual(
            zone_prompt.zone_of(heading, [heading, photo]), 'LEFT SIDE'
        )

    def test_heading_with_empty_slide_beside_it_is_a_top_band(self):
        heading = {'id': 'el_1', 'type': 'title',
                   'position': {'x': 2, 'y': 22, 'width': 60, 'height': 12}}
        photo = {'id': 'el_2', 'type': 'image',
                 'position': {'x': 36, 'y': 39, 'width': 62, 'height': 58}}
        self.assertEqual(zone_prompt.zone_of(heading, [heading, photo]), 'TOP')

    def test_a_grazing_neighbour_does_not_count(self):
        heading = {'id': 'el_1', 'type': 'title',
                   'position': {'x': 4, 'y': 6, 'width': 55, 'height': 10}}
        grid = {'id': 'el_2', 'type': 'image_grid',
                'position': {'x': 82, 'y': 15, 'width': 8, 'height': 78}}
        self.assertEqual(zone_prompt.zone_of(heading, [heading, grid]), 'TOP')

    def test_prompt_quotes_every_bullet_separately(self):
        slide = {
            'elements': [{
                'id': 'el_1', 'type': 'bullet_list',
                'content': 'Первый\nВторой\nТретий',
                'position': {'x': 4, 'y': 40, 'width': 30, 'height': 30},
                'style': {'marker_style': 'numbered'},
            }]
        }
        prompt = zone_prompt.build_zone_prompt(slide, 'brief', 1, 2)
        self.assertIn('a numbered list', prompt)
        for item in ('Первый', 'Второй', 'Третий'):
            self.assertIn(f'"{item}"', prompt)

    def test_prompt_is_substantially_shorter_than_the_detailed_one(self):
        brief = brief_as_text(build_brief(VALID_ANSWERS))
        for template in templates_repo.list_templates():
            for page, slide in templates_repo.load_pages(template['id']):
                short = zone_prompt.build_zone_prompt(slide, brief, page, 2)
                long = prompt_builder.build_image_prompt(slide, brief, page, 2)
                self.assertLess(len(short), len(long))

    def test_brief_is_marked_as_context_not_copy(self):
        slide = {'elements': []}
        prompt = zone_prompt.build_zone_prompt(slide, 'Event: a summit.', 1, 2)
        self.assertIn('do not print it on the slide', prompt)

    def test_brand_name_reaches_the_zone_prompt(self):
        slide = {'brand_name': 'Сфера', 'elements': []}
        prompt = zone_prompt.build_zone_prompt(slide, 'brief', 1, 2)
        self.assertIn('"Сфера"', prompt)


@override_settings(IMAGE_PROMPT_STYLE='detailed')
class PromptStyleSwitchTests(TestCase):
    def test_detailed_style_uses_the_coordinate_builder(self):
        slide = templates_repo.load_pages('template-3')[0][1]
        prompt = generator.build_prompt(slide, 'brief', 1, 2)
        self.assertIn('ELEMENTS, in reading order', prompt)

    @override_settings(IMAGE_PROMPT_STYLE='zones')
    def test_zones_style_is_the_default_builder(self):
        slide = templates_repo.load_pages('template-3')[0][1]
        prompt = generator.build_prompt(slide, 'brief', 1, 2)
        self.assertIn('presentation slide', prompt)
        self.assertNotIn('ELEMENTS, in reading order', prompt)


class CopywriterTests(TestCase):
    def test_char_budget_scales_with_box_and_type_size(self):
        headline = {'position': {'width': 45, 'height': 12},
                    'typography': {'size': 'xlarge'}}
        body = {'position': {'width': 45, 'height': 12},
                'typography': {'size': 'small'}}
        self.assertLess(
            copywriter.char_budget(headline), copywriter.char_budget(body)
        )

    def test_apply_copy_never_touches_layout(self):
        slide = templates_repo.load_pages('template-1')[0][1]
        original = slide['elements'][0]['position']
        filled = copywriter.apply_copy(
            slide, {slide['elements'][0]['id']: 'Новый текст'}
        )
        self.assertEqual(filled['elements'][0]['content'], 'Новый текст')
        self.assertEqual(filled['elements'][0]['position'], original)

    def test_apply_copy_ignores_unknown_and_empty_values(self):
        slide = {'elements': [{'id': 'el_1', 'type': 'title', 'content': 'keep'}]}
        filled = copywriter.apply_copy(slide, {'el_9': 'x', 'el_1': '   '})
        self.assertEqual(filled['elements'][0]['content'], 'keep')

    def test_brand_name_is_written_into_logo_elements(self):
        slide = {'elements': [{'id': 'el_1', 'type': 'logo',
                               'content': 'primary logo with wordmark'}]}
        filled = copywriter.apply_copy(slide, {'brand_name': 'НОТА'})
        self.assertIn('"НОТА"', filled['elements'][0]['content'])
        self.assertEqual(filled['brand_name'], 'НОТА')

    def test_brand_name_reaches_the_image_prompt(self):
        slide = {'elements': [{'id': 'el_1', 'type': 'logo', 'content': 'logo'}]}
        filled = copywriter.apply_copy(slide, {'brand_name': 'НОТА'})
        prompt = prompt_builder.build_image_prompt(filled, 'brief', 1, 2)
        self.assertIn('The brand is called "НОТА"', prompt)

    def test_brand_name_is_not_treated_as_an_element_id(self):
        slide = {'elements': [{'id': 'el_1', 'type': 'title', 'content': 'keep'}]}
        filled = copywriter.apply_copy(slide, {'brand_name': 'НОТА'})
        self.assertEqual(filled['elements'][0]['content'], 'keep')


class QuestionsApiTests(TestCase):
    def test_returns_all_six_questions(self):
        response = self.client.get('/api/questions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['questions']), 6)

    def test_templates_endpoint(self):
        response = self.client.get('/api/templates/')
        self.assertEqual(
            [t['id'] for t in response.json()['templates']],
            ['template-1', 'template-2', 'template-3'],
        )


@override_settings(MEDIA_ROOT=MEDIA, DEMO_MODE=True, GENERATE_SYNCHRONOUSLY=True)
class GenerationApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def post(self, **overrides):
        payload = {'template_id': 'template-1', 'answers': dict(VALID_ANSWERS)}
        payload.update(overrides)
        return self.client.post(
            '/api/generations/', payload, content_type='application/json'
        )

    def test_full_flow_produces_two_images(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)

        detail = self.client.get(f'/api/generations/{response.json()["id"]}/')
        body = detail.json()
        self.assertEqual(body['status'], 'done', body['error'])
        self.assertEqual([i['page'] for i in body['images']], [1, 2])
        self.assertTrue(all(i['url'].endswith('.png') for i in body['images']))

    def test_unknown_template_is_rejected(self):
        response = self.post(template_id='template-42')
        self.assertEqual(response.status_code, 400)
        self.assertIn('template_id', response.json())

    def test_too_many_multi_choices_rejected(self):
        answers = dict(VALID_ANSWERS)
        answers['brand_attributes'] = ['premium', 'modern', 'bold', 'eco']
        response = self.post(answers=answers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('at most 3', str(response.json()))

    def test_missing_question_rejected(self):
        answers = dict(VALID_ANSWERS)
        del answers['emotion']
        response = self.post(answers=answers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('emotion', response.json()['answers'])

    def test_unknown_option_rejected(self):
        answers = dict(VALID_ANSWERS)
        answers['emotion'] = 'schadenfreude'
        response = self.post(answers=answers)
        self.assertEqual(response.status_code, 400)

    def test_single_choice_rejects_a_list(self):
        answers = dict(VALID_ANSWERS)
        answers['emotion'] = ['pride']
        response = self.post(answers=answers)
        self.assertEqual(response.status_code, 400)

    def test_failure_is_recorded_not_raised(self):
        with mock.patch(
            'app.services.generator.templates_repo.load_pages',
            side_effect=templates_repo.TemplateNotFound('boom'),
        ):
            response = self.post()
        generation = Generation.objects.get(pk=response.json()['id'])
        self.assertEqual(generation.status, Generation.Status.FAILED)
        self.assertIn('boom', generation.error)


@override_settings(MEDIA_ROOT=MEDIA, DEMO_MODE=False, GENERATE_SYNCHRONOUSLY=True)
class LiveStageTests(TestCase):
    """The real two-stage path, with the OpenAI calls stubbed."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    @mock.patch('app.services.generator.openai_client.render_image')
    @mock.patch('app.services.generator.openai_client.write_copy')
    def test_copy_from_stage_one_reaches_the_image_prompt(self, write, render):
        write.return_value = {'el_1': 'ЗАПУСК ГОДА'}
        render.return_value = b'\x89PNG\r\n\x1a\n' + b'0' * 64

        response = self.client.post(
            '/api/generations/',
            {'template_id': 'template-3', 'answers': VALID_ANSWERS},
            content_type='application/json',
        )
        generation = Generation.objects.get(pk=response.json()['id'])
        self.assertEqual(generation.status, Generation.Status.DONE, generation.error)

        first = generation.images.first()
        self.assertIn('"ЗАПУСК ГОДА"', first.prompt_used)
        self.assertEqual(
            [e for e in first.filled_layout['elements'] if e['id'] == 'el_1'][0]
            ['content'],
            'ЗАПУСК ГОДА',
        )

    @mock.patch(
        'app.services.generator.openai_client.write_copy',
        side_effect=Exception('rate limited'),
    )
    def test_api_failure_surfaces_as_failed_status(self, _write):
        response = self.client.post(
            '/api/generations/',
            {'template_id': 'template-1', 'answers': VALID_ANSWERS},
            content_type='application/json',
        )
        generation = Generation.objects.get(pk=response.json()['id'])
        self.assertEqual(generation.status, Generation.Status.FAILED)
        self.assertIn('rate limited', generation.error)
