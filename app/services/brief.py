"""Turns the user's answers into an English creative brief.

Both generation stages need the same brief -- the copy stage to know what to
write about, the image stage to know what it should look like -- so it is built
once, here, and passed to both.
"""

from app import questions


def _values(answers, key):
    value = answers.get(key)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _hints(answers, key):
    return [questions.describe(key, v) for v in _values(answers, key)]


def _labels(answers, key):
    return [questions.label(key, v) for v in _values(answers, key)]


def build_brief(answers):
    """Structured brief: English for the model, Russian labels for display."""
    event_type = _hints(answers, 'event_type')
    emotion = _hints(answers, 'emotion')
    reference = _hints(answers, 'reference')
    scale = _hints(answers, 'scale')

    return {
        'event_type': event_type[0] if event_type else 'a corporate event',
        'goals': _hints(answers, 'goals'),
        'emotion': emotion[0] if emotion else 'inspiration',
        'brand_attributes': _hints(answers, 'brand_attributes'),
        'reference': reference[0] if reference else 'a modern corporate keynote',
        'scale': scale[0] if scale else 'city-wide buzz',
        'labels': {key: _labels(answers, key) for key in questions.QUESTIONS_BY_KEY},
    }


def brief_as_text(brief):
    """The brief as a prompt fragment."""
    lines = [
        f"Event: {brief['event_type']}.",
        f"The audience should feel: {brief['emotion']}.",
        f"Creative reference: {brief['reference']}.",
        f"Reach and stature: {brief['scale']}.",
    ]
    if brief['goals']:
        lines.append(f"Business goals: {', '.join(brief['goals'])}.")
    if brief['brand_attributes']:
        lines.append(
            f"The brand must read as: {', '.join(brief['brand_attributes'])}."
        )
    return '\n'.join(lines)
