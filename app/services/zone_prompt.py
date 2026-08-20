"""Zone-based image prompt: a short brief instead of a coordinate spec.

The element-by-element prompt in :mod:`prompt_builder` states every position as
a percentage. gpt-image-1 takes that literally -- a box at ``x=2`` puts the
first glyph on the border and clips it -- while the sheer length of the spec
dilutes every individual instruction, so the composition suffers too.

This builder keeps the same source of truth but describes it the way the model
actually responds to: a handful of named zones (TOP, LEFT, RIGHT, BOTTOM), the
copy that belongs in each, and a short style tail. Exact geometry is not lost --
it stays in ``filled_layout`` for a deterministic renderer to use later.
"""

from .prompt_builder import (
    COLOR_WORDS,
    FAMILY_WORDS,
    PICTORIAL_TYPES,
    _humanize,
)

# A block this wide reads as a band across the slide rather than a column.
FULL_WIDTH = 70.0

# A heading or footer need not span the whole slide to read as a top or bottom
# band -- half the width plus a position in the top or bottom strip is enough.
BAND_WIDTH = 45.0
TOP_STRIP = 25.0
BOTTOM_STRIP = 80.0

TOP, LEFT, RIGHT, CENTRE, BOTTOM = 'TOP', 'LEFT SIDE', 'RIGHT SIDE', 'CENTRE', 'BOTTOM'
ZONE_ORDER = [TOP, LEFT, CENTRE, RIGHT, BOTTOM]


# How much of an element's height a neighbour must share before it counts as
# standing beside it. A one-unit graze is not a neighbour.
OVERLAP_RATIO = 0.25


def _bounds(element):
    position = element.get('position') or {}
    x = float(position.get('x', 0))
    y = float(position.get('y', 0))
    return x, y, x + float(position.get('width', 0)), y + float(
        position.get('height', 0)
    )


def stands_alone(element, elements):
    """True when no other element shares this one's row to its left or right.

    Separates a genuine full-width heading from the top of a left-hand column:
    both are wide and near the top, but only the heading has empty slide beside
    it. Without this a two-column layout loses its columns.
    """
    x1, y1, x2, y2 = _bounds(element)
    height = y2 - y1

    for other in elements:
        if other is element:
            continue
        ox1, oy1, ox2, oy2 = _bounds(other)
        overlap = min(y2, oy2) - max(y1, oy1)
        if height <= 0 or overlap / height < OVERLAP_RATIO:
            continue
        if ox1 >= x2 - 1 or ox2 <= x1 + 1:
            return False
    return True


def zone_of(element, elements=()):
    """Which named zone an element belongs to."""
    position = element.get('position') or {}
    x = float(position.get('x', 0))
    y = float(position.get('y', 0))
    width = float(position.get('width', 0))
    height = float(position.get('height', 0))

    centre_x = x + width / 2
    centre_y = y + height / 2

    # Anything spanning most of the slide is a band, whatever it contains.
    if width >= FULL_WIDTH:
        if centre_y < 30:
            return TOP
        if centre_y > 70:
            return BOTTOM
        return CENTRE

    # A wide-ish text block sitting in the top or bottom strip is a heading or
    # a footer, not a column. Photographs are excluded: a tall image starting
    # near the top is still a side block.
    if (
        width >= BAND_WIDTH
        and element.get('type') not in PICTORIAL_TYPES
        and stands_alone(element, elements)
    ):
        if y < TOP_STRIP:
            return TOP
        if y + height > BOTTOM_STRIP:
            return BOTTOM

    if centre_x < 40:
        return LEFT
    if centre_x > 60:
        return RIGHT
    return CENTRE


def group_by_zone(elements):
    """``{zone: [elements]}`` in zone order, each zone sorted top to bottom."""
    grouped = {}
    for element in elements:
        grouped.setdefault(zone_of(element, elements), []).append(element)
    for items in grouped.values():
        items.sort(key=lambda e: float((e.get('position') or {}).get('y', 0)))
    return {zone: grouped[zone] for zone in ZONE_ORDER if zone in grouped}


def _element_line(element):
    """One line describing an element, in the compact zone style."""
    kind = element.get('type', 'text')
    content = (element.get('content') or '').strip()
    if not content:
        return None

    if kind in PICTORIAL_TYPES:
        if kind == 'divider':
            return f'a thin divider rule ({content})'
        if kind == 'logo':
            return f'a logo mark — {content}'
        if kind in ('image', 'image_grid'):
            return f'a large, high-quality photograph: {content}'
        return f'{_humanize(kind)}: {content}'

    if kind == 'bullet_list':
        items = [line.strip() for line in content.splitlines() if line.strip()]
        marker = (element.get('style') or {}).get('marker_style')
        prefix = 'a numbered list' if marker == 'numbered' else 'a bullet list'
        bullets = '\n'.join(f'  • "{item}"' for item in items) or f'  • "{content}"'
        return f'{prefix}:\n{bullets}'

    labels = {
        'title': 'a large bold title',
        'subtitle': 'a subheading',
        'quote': 'a short pull quote',
        'text_block': 'a short paragraph',
        'footer': 'a small footer line',
    }
    return f'{labels.get(kind, "a short text line")}: "{content}"'


def typography_summary(elements):
    """One sentence covering the whole slide instead of a line per element."""
    families = []
    for element in elements:
        family = (element.get('typography') or {}).get('style')
        word = FAMILY_WORDS.get(family)
        if word and word not in families:
            families.append(word)
    if not families:
        return 'Clean, modern typography with a clear size hierarchy.'
    return (
        f'Typography: {" and ".join(families)}, sharp and highly legible, '
        f'with a clear size hierarchy between title and body.'
    )


def palette_summary(slide):
    style = slide.get('style') or {}
    colours = []
    for element in slide.get('elements', []):
        colour = (element.get('style') or {}).get('color')
        word = COLOR_WORDS.get(colour)
        if word and word not in colours:
            colours.append(word)
    accent = next(
        (
            (element.get('style') or {}).get('accent_color')
            for element in slide.get('elements', [])
            if (element.get('style') or {}).get('accent_color')
        ),
        None,
    )
    parts = [f'Background: {_humanize(style.get("background")) or "plain white"}.']
    if colours:
        parts.append(f'Text colours: {", ".join(colours)}.')
    if accent:
        parts.append(f'Accent colour: {_humanize(accent)}.')
    return ' '.join(parts)


def build_zone_prompt(slide, brief_text, page, total_pages):
    """A short, zone-based prompt for one filled slide."""
    style = slide.get('style') or {}
    elements = slide.get('elements') or []

    lines = [
        'Create a professional modern presentation slide.',
        '',
        f'{slide.get("aspect_ratio", "16:9")} presentation layout, '
        f'{_humanize(style.get("overall_style")) or "clean corporate"} design. '
        f'Slide {page} of {total_pages}.',
        '',
        'CONTEXT (informs the imagery and mood, do not print it on the slide):',
        brief_text,
        '',
    ]

    if slide.get('brand_name'):
        lines += [
            f'The brand is called "{slide["brand_name"]}". Any wordmark on the '
            f'slide reads exactly that and nothing else.',
            '',
        ]

    for zone, items in group_by_zone(elements).items():
        described = [line for line in map(_element_line, items) if line]
        if not described:
            continue
        lines.append(f'{zone}:')
        lines += [f'- {line}' for line in described]
        lines.append('')

    lines += [
        palette_summary(slide),
        typography_summary(elements),
        '',
        'Clear visual hierarchy, minimalistic background, modern geometric '
        'elements, generous margins, clean spacing, balanced composition, '
        'premium infographic style, suitable for a business presentation.',
        '',
        'All copy is in Russian Cyrillic. Reproduce every quoted string exactly '
        'as written, correctly spelled, with well-formed Cyrillic letters. '
        'Keep all text comfortably inside the slide — no letter may touch or '
        'be cut off by the edge.',
        '',
        'No clutter, no extra headings or captions beyond those listed, no '
        'lorem ipsum, no watermarks, no photorealistic full-slide background. '
        'The result must clearly look like a presentation slide.',
    ]

    return '\n'.join(lines).strip()
