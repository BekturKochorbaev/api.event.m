"""Read-only access to the slide layout templates on disk.

Templates are plain JSON files named ``template<N>-<PAGE>.json``: one file per
page, so ``template1-1.json`` and ``template1-2.json`` are the two pages of the
same presentation. Nothing about them is stored in the database -- they are
static assets shipped with the project.
"""

import json
import re
from functools import lru_cache

from django.conf import settings

FILENAME_RE = re.compile(r'^template(\d+)-(\d+)\.json$')


class TemplateNotFound(Exception):
    pass


def _template_id(number):
    return f'template-{number}'


def _parse_number(template_id):
    """``"template-1"`` -> ``1``. Returns None for anything else."""
    match = re.fullmatch(r'template-(\d+)', str(template_id or ''))
    return int(match.group(1)) if match else None


@lru_cache(maxsize=1)
def _scan():
    """Map ``{template_number: {page_number: parsed_json}}``.

    Cached: the files are static, so one read at first use is enough. Call
    ``_scan.cache_clear()`` after touching them (the tests do).
    """
    found = {}
    for path in sorted(settings.TEMPLATES_DIR.glob('*.json')):
        match = FILENAME_RE.match(path.name)
        if not match:
            continue
        number, page = int(match.group(1)), int(match.group(2))
        with path.open(encoding='utf-8') as fh:
            found.setdefault(number, {})[page] = json.load(fh)
    return found


def list_templates():
    """Every template, ordered by number, as plain dicts for the API."""
    scanned = _scan()
    return [
        {
            'id': _template_id(number),
            'pages': len(pages),
            'preview': _preview(pages),
        }
        for number, pages in sorted(scanned.items())
    ]


def _preview(pages):
    """Short human-readable hint about a template, taken from its first page."""
    first = pages[min(pages)].get('slide', {})
    style = first.get('style', {})
    return {
        'overall_style': style.get('overall_style'),
        'background': style.get('background'),
        'aspect_ratio': first.get('aspect_ratio'),
    }


def template_exists(template_id):
    return _parse_number(template_id) in _scan()


def load_pages(template_id):
    """Ordered ``[(page_number, slide_dict), ...]`` for one template.

    The returned dicts are deep copies, so callers may fill them in freely
    without corrupting the cache.
    """
    number = _parse_number(template_id)
    pages = _scan().get(number)
    if not pages:
        raise TemplateNotFound(f'unknown template: {template_id!r}')
    return [
        (page, json.loads(json.dumps(pages[page].get('slide', pages[page]))))
        for page in sorted(pages)
    ]
