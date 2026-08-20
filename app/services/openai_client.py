"""Thin wrapper over the OpenAI calls the generator makes.

Deliberately Django-free below the settings read: it takes dicts and strings and
returns text and bytes, which keeps it trivial to stub out in tests and behind
``DEMO_MODE``.
"""

import base64
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """A stage failed after exhausting the SDK's own retries."""


def _client():
    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise GenerationError('OPENAI_API_KEY is not set')
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


def write_copy(prompt):
    """Run the copy stage. Returns ``{element_id: text}``."""
    try:
        response = _client().chat.completions.create(
            model=settings.OPENAI_TEXT_MODEL,
            response_format={'type': 'json_object'},
            messages=[{'role': 'user', 'content': prompt}],
        )
        payload = json.loads(response.choices[0].message.content)
    except GenerationError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as `error`
        raise GenerationError(f'copy stage failed: {exc}') from exc

    if not isinstance(payload, dict):
        raise GenerationError('copy stage returned a non-object payload')
    return {key: value for key, value in payload.items() if isinstance(value, str)}


def render_image(prompt):
    """Run the image stage. Returns PNG bytes."""
    try:
        response = _client().images.generate(
            model=settings.OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=settings.OPENAI_IMAGE_SIZE,
            quality=settings.OPENAI_IMAGE_QUALITY,
            n=1,
        )
    except GenerationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(f'image stage failed: {exc}') from exc

    if not response.data:
        raise GenerationError('image stage returned no data')

    item = response.data[0]
    if getattr(item, 'b64_json', None):
        return base64.b64decode(item.b64_json)
    raise GenerationError('image stage returned no inline image data')
