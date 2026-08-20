"""OpenAPI schemas for the function-based views.

drf_yasg cannot introspect an ``@api_view``'s request body, and ``AnswersField``
is a custom field it would render as a bare string anyway. Both problems are
solved by describing the body explicitly here -- and since the description is
generated from ``questions.QUESTIONS`` and the template folder, the Swagger page
cannot drift away from what the API actually accepts.
"""

from drf_yasg import openapi

from . import questions, templates_repo


def _answer_property(question):
    if question['type'] in (questions.TEXT, questions.DATE):
        return openapi.Schema(
            type=openapi.TYPE_STRING,
            description=question['title'],
            example=question.get('placeholder', ''),
        )

    values = [option['value'] for option in question['options']]
    description = '{title} ({labels})'.format(
        title=question['title'],
        labels=', '.join(
            f'{o["value"]} — {o["label"]}' for o in question['options']
        ),
    )

    if question['type'] == questions.SINGLE:
        return openapi.Schema(
            type=openapi.TYPE_STRING,
            enum=values,
            description=description,
            example=values[0],
        )

    return openapi.Schema(
        type=openapi.TYPE_ARRAY,
        items=openapi.Items(type=openapi.TYPE_STRING, enum=values),
        max_items=question['max_choices'],
        description=f'{description}. Не более {question["max_choices"]}.',
        example=values[:question['max_choices']],
    )


ANSWERS_SCHEMA = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='Ответы на вопросы анкеты. Обязательные помечены в required.',
    required=[
        question['key']
        for question in questions.QUESTIONS
        if questions.is_required(question)
    ],
    properties={
        question['key']: _answer_property(question)
        for question in questions.QUESTIONS
    },
)


def _template_ids():
    """Available template ids, or None if the folder cannot be read yet."""
    try:
        return [template['id'] for template in templates_repo.list_templates()]
    except OSError:
        return None


def _template_property():
    ids = _template_ids()
    return openapi.Schema(
        type=openapi.TYPE_STRING,
        enum=ids,
        description='Идентификатор шаблона из GET /api/templates/.',
        example=ids[0] if ids else 'template-1',
    )


def _example_answers():
    example = {}
    for question in questions.QUESTIONS:
        if question['type'] in (questions.TEXT, questions.DATE):
            example[question['key']] = question.get('placeholder', '')
            continue
        values = [option['value'] for option in question['options']]
        example[question['key']] = (
            values[0] if question['type'] == questions.SINGLE
            else values[:question['max_choices']]
        )
    return example


GENERATION_REQUEST = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['template_id', 'answers'],
    properties={
        'template_id': _template_property(),
        'answers': ANSWERS_SCHEMA,
    },
    example={
        'template_id': (_template_ids() or ['template-1'])[0],
        'answers': _example_answers(),
    },
)

QUESTIONS_RESPONSE = openapi.Response(
    'Вопросы для формы, в порядке показа.',
    examples={
        'application/json': {
            'questions': [
                {
                    'key': question['key'],
                    'type': question['type'],
                    'max_choices': question['max_choices'],
                    'title': question['title'],
                    'subtitle': question['subtitle'],
                    'options': question['options'][:2] + [{'...': '...'}],
                }
                for question in questions.QUESTIONS[:2]
            ]
            + [{'...': '...'}]
        }
    },
)

TEMPLATES_RESPONSE = openapi.Response(
    'Доступные шаблоны презентаций.',
    examples={'application/json': {'templates': templates_repo.list_templates()}}
    if _template_ids() else None,
)
