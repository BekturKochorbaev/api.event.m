from rest_framework import serializers

from . import questions, templates_repo
from .models import Generation, GeneratedImage


class AnswersField(serializers.Field):
    """Validates the brief against the question definitions.

    Single-choice questions take a string, multi-choice take a list capped at
    the question's ``max_choices``, text/date take a free string; every option
    value must be a known one. Questions marked ``required`` must be present --
    a partial brief on those produces a generic deck, a worse failure than a
    clear 400. Optional questions (name aside: date, audience, when/where) may
    be omitted.
    """

    def to_representation(self, value):
        return value

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Expected an object of answers.')

        errors, cleaned = {}, {}
        for question in questions.QUESTIONS:
            key = question['key']
            allowed = questions.options_by_value(key)
            required = questions.is_required(question)

            if key not in data or data[key] in (None, '', []):
                if required:
                    errors[key] = 'This question is required.'
                continue

            value = data[key]

            if question['type'] in (questions.TEXT, questions.DATE):
                if not isinstance(value, str):
                    errors[key] = 'Expected a text value.'
                elif len(value.strip()) > 120:
                    errors[key] = 'Keep it under 120 characters.'
                elif not value.strip() and required:
                    errors[key] = 'This question is required.'
                elif value.strip():
                    cleaned[key] = value.strip()
                continue

            if question['type'] == questions.SINGLE:
                if isinstance(value, list):
                    errors[key] = 'Expected a single value, not a list.'
                elif value not in allowed:
                    errors[key] = f'Unknown option: {value!r}.'
                else:
                    cleaned[key] = value
                continue

            if not isinstance(value, list):
                errors[key] = 'Expected a list of values.'
            elif len(value) > question['max_choices']:
                errors[key] = f'Choose at most {question["max_choices"]} options.'
            elif len(set(value)) != len(value):
                errors[key] = 'Duplicate options are not allowed.'
            elif [v for v in value if v not in allowed]:
                unknown = ', '.join(repr(v) for v in value if v not in allowed)
                errors[key] = f'Unknown options: {unknown}.'
            else:
                cleaned[key] = value

        unexpected = set(data) - set(questions.QUESTIONS_BY_KEY)
        if unexpected:
            errors['non_field_errors'] = (
                f'Unknown questions: {", ".join(sorted(unexpected))}.'
            )

        if errors:
            raise serializers.ValidationError(errors)
        return cleaned


class GeneratedImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedImage
        fields = ['page', 'url']

    def get_url(self, obj):
        request = self.context.get('request')
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


class GenerationSerializer(serializers.ModelSerializer):
    images = GeneratedImageSerializer(many=True, read_only=True)

    class Meta:
        model = Generation
        fields = [
            'id', 'template_id', 'answers', 'status', 'error',
            'demo_mode', 'images', 'created_at',
        ]


class GenerationCreateSerializer(serializers.Serializer):
    template_id = serializers.CharField()
    answers = AnswersField()
    # optional brand logo as a data URL / base64 string, decoded in the view
    logo = serializers.CharField(required=False, allow_blank=True)

    def validate_template_id(self, value):
        if not templates_repo.template_exists(value):
            available = ', '.join(t['id'] for t in templates_repo.list_templates())
            raise serializers.ValidationError(
                f'Unknown template {value!r}. Available: {available}.'
            )
        return value
