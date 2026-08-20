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
    time_of_day = _hints(answers, 'time_of_day')
    venue = _hints(answers, 'venue')

    return {
        'event_type': event_type[0] if event_type else 'a corporate event',
        'goals': _hints(answers, 'goals'),
        'emotion': emotion[0] if emotion else 'inspiration',
        'brand_attributes': _hints(answers, 'brand_attributes'),
        'reference': reference[0] if reference else 'a modern corporate keynote',
        'scale': scale[0] if scale else 'city-wide buzz',
        # concrete, event-specific facts (free text passes straight through)
        'event_name': (answers.get('event_name') or '').strip(),
        'event_date': (answers.get('event_date') or '').strip(),
        'audience': _hints(answers, 'audience'),
        'time_of_day': time_of_day[0] if time_of_day else '',
        'venue': venue[0] if venue else '',
        'labels': {key: _labels(answers, key) for key in questions.QUESTIONS_BY_KEY},
    }


def brief_as_text(brief):
    """The brief as a prompt fragment."""
    lines = []
    if brief['event_name']:
        lines.append(
            f'The event is named "{brief["event_name"]}". Use this exact name, '
            f'spelled exactly like this, as the event/brand name on the slides; '
            f'do not invent a different one.'
        )
    lines.append(f"Event: {brief['event_type']}.")
    if brief['event_date']:
        lines.append(f"Date: {brief['event_date']}.")
    lines.append(f"The audience should feel: {brief['emotion']}.")
    lines.append(f"Creative reference: {brief['reference']}.")
    lines.append(f"Reach and stature: {brief['scale']}.")
    if brief['audience']:
        lines.append(f"Who attends: {', '.join(brief['audience'])}.")
    setting = ' and '.join(p for p in (brief['time_of_day'], brief['venue']) if p)
    if setting:
        lines.append(f"Setting: {setting}.")
    if brief['goals']:
        lines.append(f"Business goals: {', '.join(brief['goals'])}.")
    if brief['brand_attributes']:
        lines.append(
            f"The brand must read as: {', '.join(brief['brand_attributes'])}."
        )
    return '\n'.join(lines)
