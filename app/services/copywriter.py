"""Stage one: fill a layout's ``content`` fields with real copy.

The model is asked only for a flat ``{element_id: text}`` map, never for the
layout itself. Positions, typography and styles are merged in locally
afterwards, so a hallucinated or malformed response can cost us the copy but can
never corrupt the design.
"""

import json

from .prompt_builder import PICTORIAL_TYPES, _humanize

# Roughly how many characters fit in a box, per unit of the 100x100 canvas.
# Tuned so a 45x12 headline box lands near a dozen words rather than a
# paragraph -- image models mangle text blocks that overflow their container.
DENSITY = 0.55
MIN_BUDGET = 12
MAX_BUDGET = 320

# Reserved key in the copy response. Templates ask for logos "with a wordmark",
# and with no brand name to put there the image model falls back to LOREM IPSUM,
# so the copy stage has to invent one and we feed it into every logo element.
BRAND_KEY = 'brand_name'


SIZE_SCALE = {
    'xsmall': 1.6, 'small': 1.25, 'medium': 1.0, 'large': 0.55, 'xlarge': 0.32
}

# Area alone overestimates badly for display type: a large box set in xlarge
# still only holds a couple of lines. These caps keep headlines headline-length,
# which is also the single biggest lever against text overflowing the slide.
SIZE_CAP = {
    'xsmall': 300, 'small': 260, 'medium': 180, 'large': 100, 'xlarge': 60
}


def char_budget(element):
    """How much text this element's box can hold before it overflows."""
    position = element.get('position') or {}
    area = float(position.get('width', 0)) * float(position.get('height', 0))
    size = (element.get('typography') or {}).get('size', 'medium')
    scale = SIZE_SCALE.get(size, 1.0)
    cap = min(MAX_BUDGET, SIZE_CAP.get(size, MAX_BUDGET))
    return int(max(MIN_BUDGET, min(cap, area * DENSITY * scale)))


def writable_elements(slide):
    """Elements whose ``content`` is literal text the model should write."""
    return [
        element
        for element in slide.get('elements', [])
        if element.get('type') not in PICTORIAL_TYPES
        and (element.get('content') or '').strip()
    ]


def build_copy_prompt(slide, brief_text, page, total_pages):
    specs = []
    for element in writable_elements(slide):
        style = element.get('style') or {}
        line = [
            f'- id "{element["id"]}" ({_humanize(element.get("type"))})',
            f'  purpose: {_humanize(element.get("role")) or "supporting copy"}',
            f'  the template asks for: {element.get("content")}',
            f'  hard limit: {char_budget(element)} characters',
        ]
        for key in ('item_count', 'count'):
            if style.get(key):
                line.append(
                    f'  must contain exactly {style[key]} items, '
                    f'each within the character limit'
                )
        specs.append('\n'.join(line))

    return f"""You are a senior event copywriter. Write the on-slide copy for
slide {page} of a {total_pages}-slide event pitch deck.

CREATIVE BRIEF
{brief_text}

Write in Russian. Match the tone to the brief: the emotion and brand attributes
above decide the register, and the creative reference decides the rhythm of the
phrasing.

Rules:
- This is copy that goes ON a slide. Short, concrete, confident. No filler,
  no marketing cliches, no exclamation marks.
- Obey every character limit strictly. Going over ruins the layout.
- Invent a plausible event name, and reuse it consistently across elements.
- Never write placeholder text, never restate the instruction back to me.
- For list elements, separate items with a newline and no bullet characters.

Write copy for these elements:

{chr(10).join(specs)}

Also return "{BRAND_KEY}": the brand or event name as it should appear in a
logo wordmark. One or two words, no tagline, no quotes, no legal suffix.

Return a JSON object mapping each element id to its copy, and nothing else.
Example shape: {{"{BRAND_KEY}": "...", "el_1": "...", "el_2": "..."}}"""


def apply_copy(slide, copy_map):
    """Merge ``{id: text}`` into a copy of the slide. Unknown ids are ignored."""
    filled = json.loads(json.dumps(slide))
    brand = copy_map.get(BRAND_KEY)
    brand = brand.strip() if isinstance(brand, str) else ''
    if brand:
        filled[BRAND_KEY] = brand

    for element in filled.get('elements', []):
        if element.get('type') == 'logo' and brand:
            element['content'] = (
                f'{element.get("content", "logo")}. The wordmark reads exactly '
                f'"{brand}" — never any other name and never placeholder text'
            )
            continue

        text = copy_map.get(element.get('id'))
        if isinstance(text, str) and text.strip():
            element['content'] = text.strip()
    return filled
