"""Translates a filled slide layout into an image-generation prompt.

Image models do not parse JSON well and do not honour numeric coordinates, so
handing them the raw template wastes most of the layout information. Instead
every machine-readable value is mapped into the spatial and typographic language
the model does respond to: ``{"x": 4, "y": 8}`` becomes "upper-left", ``{"size":
"xlarge", "style": "serif"}`` becomes "very large serif".

The vocabulary below covers every value present in the shipped templates; the
mappings degrade to the raw value (de-underscored) for anything new, so an added
template renders a slightly rougher prompt rather than crashing.
"""

CANVAS = 100.0

# Templates place text as close as x=2 to the edge. Taken literally, the image
# model starts the first glyph at the very border and clips it. Text boxes
# inside this margin are therefore described as inset, and the safe area is
# restated as a hard requirement. Pictorial elements are exempt -- a photo
# hugging the edge is intentional.
SAFE_MARGIN = 6.0

SIZE_WORDS = {
    'xsmall': 'very small',
    'small': 'small',
    'medium': 'medium-sized',
    'large': 'large',
    'xlarge': 'very large',
}

WEIGHT_WORDS = {
    'regular': 'regular-weight',
    'medium': 'medium-weight',
    'semibold': 'semibold',
    'bold': 'bold',
    'extrabold': 'extra-bold',
}

FAMILY_WORDS = {
    'serif': 'serif',
    'sans-serif': 'sans-serif',
    'italic_serif': 'italic serif',
}

COLOR_WORDS = {
    'dark': 'near-black',
    'light': 'white',
    'medium': 'mid-grey',
    'accent': 'the accent colour',
    'accent_bright': 'a bright accent colour',
    'dark_silhouette': 'a dark silhouette',
    'mixed_dark_and_accent': 'near-black with accent-coloured highlights',
}

ELEMENT_WORDS = {
    'title': 'Headline',
    'subtitle': 'Subheading',
    'text': 'Text label',
    'text_block': 'Paragraph block',
    'bullet_list': 'List',
    'quote': 'Pull quote',
    'divider': 'Divider rule',
    'image': 'Photograph',
    'image_grid': 'Grid of photographs',
    'logo': 'Logo',
    'icon': 'Icon',
    'shape': 'Shape',
    'footer': 'Footer strip',
}

# Elements whose `content` is a description of artwork, not literal text.
PICTORIAL_TYPES = {'image', 'image_grid', 'logo', 'icon', 'shape', 'divider'}


def _humanize(value):
    return str(value).replace('_', ' ') if value else ''


def _horizontal_band(centre):
    if centre < 30:
        return 'left'
    if centre < 45:
        return 'centre-left'
    if centre <= 55:
        return 'horizontally centred'
    if centre <= 70:
        return 'centre-right'
    return 'right'


def _vertical_band(centre):
    if centre < 25:
        return 'top'
    if centre < 45:
        return 'upper-middle'
    if centre <= 55:
        return 'vertically centred'
    if centre <= 75:
        return 'lower-middle'
    return 'bottom'


def edge_hugs(position, pictorial=False):
    """Which slide edges a text box sits too close to.

    Returns the offending edge names. Empty for pictorial elements, which are
    allowed -- and often meant -- to bleed off the slide.
    """
    if pictorial or not position:
        return []

    x = float(position.get('x', 0))
    y = float(position.get('y', 0))
    right = x + float(position.get('width', 0))
    bottom = y + float(position.get('height', 0))

    edges = []
    if x < SAFE_MARGIN:
        edges.append('left')
    if y < SAFE_MARGIN:
        edges.append('top')
    if right > CANVAS - SAFE_MARGIN:
        edges.append('right')
    if bottom > CANVAS - SAFE_MARGIN:
        edges.append('bottom')
    return edges


def inset_position(position):
    """Squeeze a text box into the safe area.

    Asking the model to "hold clear of the edge" does not work -- it reads the
    box as flush-left and starts the first glyph on the border, clipping it.
    Remapping the coordinates instead means the position we describe is already
    safe, so there is no instruction left for the model to disobey.
    """
    if not position:
        return position

    span = CANVAS - 2 * SAFE_MARGIN
    scale = span / CANVAS
    inset = dict(position)
    for origin, extent in (('x', 'width'), ('y', 'height')):
        if origin in position:
            inset[origin] = SAFE_MARGIN + float(position[origin]) * scale
        if extent in position:
            inset[extent] = float(position[extent]) * scale
    return inset


def describe_position(position, pictorial=False):
    """``{"x":4,"y":8,"width":45,"height":12}`` -> spatial English."""
    if not position:
        return 'placed as the composition requires'

    x = float(position.get('x', 0))
    y = float(position.get('y', 0))
    width = float(position.get('width', 0))
    height = float(position.get('height', 0))

    where = (
        f'{_vertical_band(y + height / 2)} '
        f'{_horizontal_band(x + width / 2)}'
    ).replace('vertically centred horizontally centred', 'dead centre')

    parts = [f'positioned {where} of the slide']
    if width >= 88:
        parts.append('spanning the full width')
    elif width:
        parts.append(f'about {round(width)}% of the slide width')
    if height >= 88:
        parts.append('running the full height')
    elif height:
        parts.append(f'about {round(height)}% of the height')

    if not pictorial:
        # State the offsets outright. A named band alone ("left") reads as
        # flush-left and gets the first letter clipped.
        parts.append(
            f'its left edge beginning {round(x)}% in from the slide border '
            f'and its first line starting {round(y)}% down from the top'
        )
    return ', '.join(parts)


def describe_typography(typography):
    if not typography:
        return ''
    words = [
        SIZE_WORDS.get(typography.get('size'), _humanize(typography.get('size'))),
        WEIGHT_WORDS.get(typography.get('weight'), _humanize(typography.get('weight'))),
        FAMILY_WORDS.get(typography.get('style'), _humanize(typography.get('style'))),
    ]
    phrase = ' '.join(w for w in words if w)
    detail = []
    if phrase:
        detail.append(f'set in {phrase} type')
    if typography.get('alignment'):
        detail.append(f"{_humanize(typography['alignment'])}-aligned")
    if typography.get('letter_spacing') == 'wide':
        detail.append('with wide letter spacing')
    elif typography.get('letter_spacing'):
        detail.append(f"with {_humanize(typography['letter_spacing'])} letter spacing")
    return ', '.join(detail)


def describe_style(style):
    """Element-level style keys -> English, colour first."""
    if not style:
        return ''
    parts = []
    if 'color' in style:
        parts.append(f"coloured {COLOR_WORDS.get(style['color'], _humanize(style['color']))}")

    shape = style.get('shape')
    if shape == 'rectangle_full_bleed':
        parts.append('full-bleed rectangle running off the slide edge')
    elif shape:
        parts.append(f'{_humanize(shape)} shaped')
    if style.get('border_radius') == 'full':
        parts.append('fully rounded')

    for key, template in (
        ('marker_style', 'markers are {}'),
        ('accent_color', 'accent colour is {}'),
        ('thickness', '{} thickness'),
        ('item_count', 'exactly {} items'),
        ('count', 'exactly {} of them'),
        ('separator', 'items separated by a {}'),
        ('connector_style', 'connected with a {}'),
        ('edge_treatment', '{}'),
        ('background_or_block', 'rendered as a {}'),
        ('aspect_ratio', '{} aspect ratio'),
    ):
        if style.get(key):
            parts.append(template.format(_humanize(style[key])))

    if style.get('icon_above'):
        parts.append('with a small icon directly above it')
    if style.get('border') == 'none':
        parts.append('no border')
    return ', '.join(parts)


def _reading_order(elements):
    """Top-to-bottom, then left-to-right -- how a viewer scans the slide."""
    def key(element):
        pos = element.get('position') or {}
        return (float(pos.get('y', 0)), float(pos.get('x', 0)))

    return sorted(elements, key=key)


def describe_element(index, element):
    kind = element.get('type', 'text')
    pictorial = kind in PICTORIAL_TYPES
    heading = ELEMENT_WORDS.get(kind, _humanize(kind) or 'Element')
    content = (element.get('content') or '').strip()

    position = element.get('position')
    if not pictorial:
        position = inset_position(position)

    lines = [f'{index}. {heading} — {describe_position(position, pictorial)}.']

    typography = describe_typography(element.get('typography'))
    if typography:
        lines.append(f'   Typography: {typography}.')

    style = describe_style(element.get('style'))
    if style:
        lines.append(f'   Style: {style}.')

    if content:
        if pictorial:
            lines.append(f'   Depicts: {content}')
        else:
            lines.append(f'   Renders this exact text: "{content}"')

    if element.get('role'):
        lines.append(f'   Purpose: {_humanize(element["role"])}.')

    return '\n'.join(lines)


def build_image_prompt(slide, brief_text, page, total_pages):
    """Full prompt for one slide.

    ``slide`` must already have its ``content`` fields filled with the real copy
    -- this stage only describes, it never invents.
    """
    style = slide.get('style') or {}
    layout = slide.get('layout') or {}
    elements = slide.get('elements') or []

    margin = round(SAFE_MARGIN)
    header = [
        'Design a single presentation slide, rendered as a finished, '
        'production-quality graphic design — not a photograph of a screen, '
        'not a mockup in a room.',
        '',
        f'Slide {page} of {total_pages}. '
        f'Aspect ratio {slide.get("aspect_ratio", "16:9")}, landscape.',
        '',
        'BEFORE ANYTHING ELSE — THE MARGIN',
        f'Treat this as an artboard with {margin}% padding locked on all four '
        f'sides. Lay out every headline, paragraph and label inside that inner '
        f'area only. The outer {margin}% band stays empty of text.',
        'The left edge is the one that goes wrong most often: the first letter '
        'of every line must be whole and clearly separated from the border. '
        'A line that begins flush against the border is a failed render.',
        'Set the type small enough that the longest line fits inside the inner '
        'area with room to spare. Shrinking the text is always correct; '
        'letting it run off the canvas never is.',
        '',
        'CREATIVE BRIEF',
        brief_text,
        '',
        'OVERALL LOOK',
        f'- Visual style: {_humanize(style.get("overall_style")) or "clean editorial"}.',
        f'- Background: {_humanize(style.get("background")) or "plain white"}.',
        f'- Dominant alignment: {_humanize(style.get("alignment")) or "left"}.',
    ]
    if layout.get('description'):
        header.append(f'- Composition: {_humanize(layout["description"])}.')
    if layout.get('columns') or layout.get('rows'):
        header.append(
            f'- Built on a {layout.get("columns", 1)}-column, '
            f'{layout.get("rows", 1)}-row grid.'
        )
    if slide.get('brand_name'):
        header.append(
            f'- The brand is called "{slide["brand_name"]}". That exact '
            f'spelling is the only name that may appear on the slide.'
        )

    body = [
        '',
        'ELEMENTS, in reading order. Treat each position as a strict '
        'instruction — the layout is the design, not a suggestion.',
        '',
    ]
    for index, element in enumerate(_reading_order(elements), start=1):
        body.append(describe_element(index, element))
        body.append('')

    footer = [
        'SAFE AREA — the most important rule',
        f'- Every piece of text must sit fully inside a margin of at least '
        f'{margin}% of the slide on all four sides. The first and last '
        f'character of every line must be completely visible.',
        '- Nothing may be cropped by the slide border. No letter may be cut '
        'in half, run off the canvas, or bleed past the edge.',
        '- If a text string is too long for its box, reduce the type size or '
        'add a line break. Never crop it, never let it overflow the slide.',
        '- Only photographs and shapes explicitly described as full-bleed may '
        'touch or cross the slide edge.',
        '',
        'TEXT ACCURACY',
        '- The copy is Russian, in Cyrillic script. Reproduce every string '
        'character for character, exactly as quoted, with correct Russian '
        'spelling. Do not transliterate, translate, abbreviate, or improvise.',
        '- Do not invent extra words, headings, captions, taglines or labels '
        'that are not listed above, and never repeat a string twice.',
        '- Use one clean, real typeface per role; every glyph must be a '
        'well-formed Cyrillic letter, never a decorative approximation.',
        '',
        'REQUIREMENTS',
        '- Respect the stated position, size and typography of every element; '
        'do not rearrange, merge, or drop any of them.',
        '- No watermarks, no UI chrome, no borders around the slide itself, '
        'no lorem ipsum, no placeholder text of any kind.',
        '- Flat, sharp, high-resolution output suitable for projection.',
    ]

    return '\n'.join(header + body + footer).strip()
