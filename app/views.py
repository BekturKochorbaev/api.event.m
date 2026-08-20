import base64
import binascii
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.decorators import method_decorator
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from . import questions, schemas, templates_repo
from .models import Generation
from .serializers import GenerationCreateSerializer, GenerationSerializer
from .services.generator import start_generation

logger = logging.getLogger(__name__)

# Cap the decoded logo so a client cannot push a huge payload through the
# JSON body. 4 MB of raw bytes is ample for any real logo.
MAX_LOGO_BYTES = 4 * 1024 * 1024


def _decode_logo(raw):
    """Turn a data URL / base64 string into a file, or None. Never raises."""
    if not raw or not isinstance(raw, str):
        return None
    payload = raw.split(',', 1)[1] if raw.startswith('data:') else raw
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        logger.warning('logo: could not decode base64, ignoring')
        return None
    if not data or len(data) > MAX_LOGO_BYTES:
        logger.warning('logo: empty or over %d bytes, ignoring', MAX_LOGO_BYTES)
        return None
    return ContentFile(data)


@swagger_auto_schema(
    method='get',
    operation_summary='Вопросы анкеты',
    operation_description=(
        'Определение формы: шесть вопросов, их тип (single/multi), лимит '
        'выбора и варианты ответов. Клиенту не нужно ничего хардкодить.'
    ),
    responses={200: schemas.QUESTIONS_RESPONSE},
)
@api_view(['GET'])
def question_list(request):
    """The wizard, served from the same definition the POST validates against."""
    return Response({'questions': questions.QUESTIONS})


@swagger_auto_schema(
    method='get',
    operation_summary='Список шаблонов',
    operation_description='Шаблоны презентаций: id, число страниц, стиль.',
    responses={200: schemas.TEMPLATES_RESPONSE},
)
@api_view(['GET'])
def template_list(request):
    return Response({'templates': templates_repo.list_templates()})


@swagger_auto_schema(
    method='post',
    operation_summary='Запустить генерацию',
    operation_description=(
        'Принимает бриф и шаблон, ставит генерацию в фон и сразу возвращает '
        'id со статусом pending. Готовые слайды забирать через '
        'GET /api/generations/{id}/, опрашивая его раз в пару секунд, пока '
        'status не станет done или failed.'
    ),
    request_body=schemas.GENERATION_REQUEST,
    responses={
        201: GenerationSerializer,
        400: 'Неизвестный шаблон, пропущенный вопрос или недопустимый вариант.',
    },
)
@api_view(['POST'])
def generation_create(request):
    """Accept a brief and start generating. Returns immediately with an id."""
    serializer = GenerationCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    generation = Generation.objects.create(
        template_id=serializer.validated_data['template_id'],
        answers=serializer.validated_data['answers'],
        demo_mode=settings.DEMO_MODE,
    )

    logo_file = _decode_logo(serializer.validated_data.get('logo'))
    if logo_file:
        generation.logo.save(f'{generation.id}.png', logo_file, save=True)

    start_generation(generation.id)

    generation.refresh_from_db()
    return Response(
        GenerationSerializer(generation, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        operation_summary='Статус генерации и готовые слайды',
        operation_description=(
            'status: pending → running → done | failed. Пока не done, '
            'images пуст. При failed причина лежит в error.'
        ),
        responses={200: GenerationSerializer, 404: 'Генерация не найдена.'},
    ),
)
class GenerationDetail(RetrieveAPIView):
    """Polled by the client until ``status`` is ``done`` or ``failed``."""

    queryset = Generation.objects.prefetch_related('images')
    serializer_class = GenerationSerializer
