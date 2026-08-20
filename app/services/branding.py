"""Deterministic brand rendering with Pillow -- no model involved.

Two jobs the image model must not touch, because both demand pixel-exact output:

* ``composite_logo`` stamps the client's own logo onto a finished slide. Asking
  a diffusion model to reproduce a logo warps it; compositing the real PNG keeps
  it crisp and correct.
* ``render_closing_slide`` draws Event M's fixed "thank you / contacts" slide.
  The phone number and email have to be exactly right, and Cyrillic text out of
  an image model is unreliable, so this slide is drawn, not generated.

Fonts are bundled (DejaVu, full Cyrillic coverage) so the output never depends on
what happens to be installed on the host.
"""

import datetime
import io
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
FONT_BOLD = os.path.join(FONT_DIR, 'DejaVuSans-Bold.ttf')
FONT_REGULAR = os.path.join(FONT_DIR, 'DejaVuSans.ttf')

# Matches OPENAI_IMAGE_SIZE (1536x1024), i.e. 3:2 -- close to 16:9.
CANVAS = (1536, 1024)

# Event M brand palette and contacts. One place to edit if they ever change.
DARK = (30, 30, 30)
LIME = (198, 242, 78)
INK = (26, 26, 26)
WHITE = (255, 255, 255)

BRAND = {
    'headline': 'БЛАГОДАРИМ ЗА ВНИМАНИЕ',
    'handle': '@eventm_agency',
    'email': 'conference@eventm.kg',
    'phone': '+996 556 82-99-78',
    'website': 'eventm.kg',
}


def _font(path, size):
    return ImageFont.truetype(path, size)


def _text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _fit_font(draw, text, path, max_width, start, minimum=28):
    """Largest font size (<= start) at which ``text`` fits ``max_width``."""
    size = start
    while size > minimum:
        if _text_size(draw, text, _font(path, size))[0] <= max_width:
            break
        size -= 4
    return _font(path, size)


def _draw_centered(draw, cx, y, text, font, fill):
    w, _ = _text_size(draw, text, font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def composite_logo(image_bytes, logo_path):
    """Stamp the client's logo into the top-left safe area of a slide."""
    try:
        base = Image.open(io.BytesIO(image_bytes)).convert('RGBA')
        logo = Image.open(logo_path).convert('RGBA')
    except Exception:  # noqa: BLE001 - a bad logo must never fail the slide
        return image_bytes

    margin = int(base.height * 0.05)
    target_h = int(base.height * 0.10)
    max_w = int(base.width * 0.24)

    ratio = logo.width / logo.height if logo.height else 1
    new_h = target_h
    new_w = int(target_h * ratio)
    if new_w > max_w:
        new_w = max_w
        new_h = int(max_w / ratio) if ratio else target_h

    logo = logo.resize((max(1, new_w), max(1, new_h)), Image.LANCZOS)
    base.alpha_composite(logo, (margin, margin))

    out = io.BytesIO()
    base.convert('RGB').save(out, format='PNG')
    return out.getvalue()


def render_closing_slide(year=None):
    """Event M's fixed thank-you slide: lime panel, headline, contacts strip."""
    year = year or datetime.date.today().year
    w, h = CANVAS
    img = Image.new('RGB', CANVAS, DARK)
    draw = ImageDraw.Draw(img)

    # Lime panel: full width, rounded bottom corners (top corners run off-canvas).
    panel_bottom = int(h * 0.60)
    radius = 64
    draw.rounded_rectangle(
        [0, -radius, w, panel_bottom], radius=radius, fill=LIME
    )

    margin = int(w * 0.09)
    inner = w - 2 * margin

    # Headline, wrapped to two lines around the natural break, auto-fit to width.
    words = BRAND['headline'].split(' ')
    line1, line2 = ' '.join(words[:-1]), words[-1]
    head_font = _fit_font(draw, line1, FONT_BOLD, inner, start=150, minimum=70)
    lh = _text_size(draw, 'Ё', head_font)[1] + int(head_font.size * 0.35)
    top = int(h * 0.12)
    _draw_centered(draw, w / 2, top, line1, head_font, INK)
    _draw_centered(draw, w / 2, top + lh, line2, head_font, INK)

    # Pills row: outlined handle pill + filled dark year pill, centred together.
    pill_font = _font(FONT_BOLD, 34)
    pad_x, pad_h = 34, 68
    handle_w = _text_size(draw, BRAND['handle'], pill_font)[0] + pad_x * 2
    year_w = _text_size(draw, str(year), pill_font)[0] + pad_x * 2
    gap = 20
    total = handle_w + gap + year_w
    x = w / 2 - total / 2
    y = top + 2 * lh + int(h * 0.05)

    draw.rounded_rectangle(
        [x, y, x + handle_w, y + pad_h], radius=pad_h // 2,
        fill=LIME, outline=INK, width=3,
    )
    _draw_centered(draw, x + handle_w / 2,
                   y + (pad_h - pill_font.size) / 2 - 4,
                   BRAND['handle'], pill_font, INK)

    x2 = x + handle_w + gap
    draw.rounded_rectangle(
        [x2, y, x2 + year_w, y + pad_h], radius=pad_h // 2, fill=INK
    )
    _draw_centered(draw, x2 + year_w / 2,
                   y + (pad_h - pill_font.size) / 2 - 4,
                   str(year), pill_font, LIME)

    # Bottom dark strip: three labelled contact columns.
    label_font = _font(FONT_BOLD, 24)
    value_font = _font(FONT_BOLD, 30)
    columns = [
        ('Email', BRAND['email']),
        ('Phone Number', BRAND['phone']),
        ('Website', BRAND['website']),
    ]
    strip_y = panel_bottom + int((h - panel_bottom) * 0.28)
    for i, (lbl, val) in enumerate(columns):
        cx = margin + inner * (i + 0.5) / len(columns)
        _draw_centered(draw, cx, strip_y, lbl, label_font, LIME)
        _draw_centered(draw, cx, strip_y + 40, val, value_font, WHITE)

    out = io.BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()
