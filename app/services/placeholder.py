"""Offline stand-in for the two OpenAI stages, used when DEMO_MODE is on.

The image it draws is a faithful wireframe of the layout: every element sits at
its true coordinates. That makes it useful beyond just unblocking a missing API
key -- it is the quickest way to see what a template actually specifies.
"""

import io

from PIL import Image, ImageDraw

from .prompt_builder import PICTORIAL_TYPES

WIDTH, HEIGHT = 1536, 864  # 16:9

INK = (32, 32, 36)
MUTED = (140, 140, 148)
ACCENT = (176, 58, 46)
PAPER = (247, 245, 241)


def fake_copy(slide):
    """Echo the template's own content hints back as the 'written' copy."""
    return {
        element['id']: f"[demo] {element.get('content', '')}"[:120]
        for element in slide.get('elements', [])
        if element.get('type') not in PICTORIAL_TYPES
    }


def _box(position):
    x = float(position.get('x', 0)) / 100 * WIDTH
    y = float(position.get('y', 0)) / 100 * HEIGHT
    w = max(float(position.get('width', 0)) / 100 * WIDTH, 2)
    h = max(float(position.get('height', 0)) / 100 * HEIGHT, 2)
    return [x, y, x + w, y + h]


def render_wireframe(slide, page):
    dark = 'black' in str((slide.get('style') or {}).get('background', ''))
    paper = (18, 18, 20) if dark else PAPER
    ink = (235, 235, 235) if dark else INK

    canvas = Image.new('RGB', (WIDTH, HEIGHT), paper)
    draw = ImageDraw.Draw(canvas)

    for element in slide.get('elements', []):
        box = _box(element.get('position') or {})
        pictorial = element.get('type') in PICTORIAL_TYPES
        draw.rectangle(box, outline=ACCENT if pictorial else MUTED, width=2)

        caption = f"{element.get('type', '?')} · {element.get('id', '')}"
        draw.text((box[0] + 8, box[1] + 6), caption, fill=ink)

        content = (element.get('content') or '')[:90]
        if content and not pictorial:
            draw.text((box[0] + 8, box[1] + 22), content, fill=ink)

    draw.text((16, HEIGHT - 24), f'DEMO MODE — page {page}', fill=ACCENT)

    buffer = io.BytesIO()
    canvas.save(buffer, format='PNG')
    return buffer.getvalue()
