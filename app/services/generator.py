"""Drives a Generation from pending to done.

Per page: fill the layout's copy (stage one), describe the filled layout as an
image prompt (stage two), render it, store the PNG plus both intermediates.
Runs off the request thread -- two slides take well over a minute.
"""

import logging
import threading

from django.core.files.base import ContentFile
from django.conf import settings
from django.db import close_old_connections

from app import templates_repo
from app.models import Generation, GeneratedImage

from . import branding, copywriter, openai_client, placeholder, prompt_builder, zone_prompt
from .brief import brief_as_text, build_brief
from .openai_client import GenerationError

logger = logging.getLogger(__name__)


def build_prompt(filled, brief_text, page, total_pages):
    """Image prompt for a filled slide, in the configured style.

    ``zones`` is the default: a short brief the model composes well from.
    ``detailed`` is the original coordinate-by-coordinate spec, kept because it
    is the more faithful description of the template even though the model
    follows it less willingly.
    """
    if getattr(settings, 'IMAGE_PROMPT_STYLE', 'zones') == 'detailed':
        return prompt_builder.build_image_prompt(
            filled, brief_text, page, total_pages
        )
    return zone_prompt.build_zone_prompt(filled, brief_text, page, total_pages)


def generate_page(slide, brief_text, page, total_pages, demo_mode):
    """One slide: copy stage, prompt stage, image stage."""
    if demo_mode:
        copy_map = placeholder.fake_copy(slide)
    else:
        copy_map = openai_client.write_copy(
            copywriter.build_copy_prompt(slide, brief_text, page, total_pages)
        )

    filled = copywriter.apply_copy(slide, copy_map)
    prompt = build_prompt(filled, brief_text, page, total_pages)

    if demo_mode:
        image_bytes = placeholder.render_wireframe(filled, page)
    else:
        image_bytes = openai_client.render_image(prompt)

    return filled, prompt, image_bytes


def run_generation(generation_id):
    """Execute a generation to completion. Never raises; records failures."""
    close_old_connections()
    try:
        generation = Generation.objects.get(pk=generation_id)
    except Generation.DoesNotExist:
        logger.warning('run_generation: %s no longer exists', generation_id)
        return

    Generation.objects.filter(pk=generation_id).update(
        status=Generation.Status.RUNNING
    )

    try:
        pages = templates_repo.load_pages(generation.template_id)
        brief_text = brief_as_text(build_brief(generation.answers))
        total = len(pages)
        logo_path = generation.logo.path if generation.logo else None

        for page, slide in pages:
            filled, prompt, image_bytes = generate_page(
                slide, brief_text, page, total, generation.demo_mode
            )
            if logo_path:
                image_bytes = branding.composite_logo(image_bytes, logo_path)
            image = GeneratedImage(
                generation=generation,
                page=page,
                filled_layout=filled,
                prompt_used=prompt,
            )
            image.image.save(
                f'{generation.id}/page-{page}.png',
                ContentFile(image_bytes),
                save=False,
            )
            image.save()

        # Fixed Event M closing slide, always the last page. Drawn, not
        # generated, so the contacts are exact -- see services/branding.py.
        closing_page = total + 1
        closing = GeneratedImage(generation=generation, page=closing_page)
        closing.image.save(
            f'{generation.id}/page-{closing_page}.png',
            ContentFile(branding.render_closing_slide()),
            save=False,
        )
        closing.save()

        generation.status = Generation.Status.DONE
        generation.error = ''
    except (GenerationError, templates_repo.TemplateNotFound) as exc:
        logger.exception('generation %s failed', generation_id)
        generation.status = Generation.Status.FAILED
        generation.error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a stuck 'running' row is worse
        logger.exception('generation %s failed unexpectedly', generation_id)
        generation.status = Generation.Status.FAILED
        generation.error = f'{type(exc).__name__}: {exc}'
    finally:
        generation.save(update_fields=['status', 'error', 'updated_at'])
        close_old_connections()


def start_generation(generation_id):
    """Kick off a generation in the background.

    A bare thread is enough for the demo. If this ever needs to survive a
    restart, swap the body for a Celery ``.delay()`` -- ``run_generation`` is
    already a self-contained, id-addressed unit of work.
    """
    if getattr(settings, 'GENERATE_SYNCHRONOUSLY', False):
        run_generation(generation_id)
        return

    thread = threading.Thread(
        target=run_generation, args=(generation_id,), daemon=True
    )
    thread.start()
