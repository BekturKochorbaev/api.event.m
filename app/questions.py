"""The six-question brief the user fills in before generating a deck.

Kept here as data rather than in the database: the wizard is fixed for the demo,
and one definition drives both ``GET /api/questions/`` and the POST validation,
so the form the client renders can never drift from what the server accepts.

Every option carries an English ``hint`` alongside its Russian ``label``. The
labels are what the user picked; the hints are what the prompt builder feeds the
model, which reasons about a Russian brief far more reliably in English.
"""

SINGLE = 'single'
MULTI = 'multi'


def _opt(value, label, hint):
    return {'value': value, 'label': label, 'hint': hint}


QUESTIONS = [
    {
        'key': 'event_type',
        'type': SINGLE,
        'max_choices': 1,
        'title': 'Что вы хотите провести?',
        'subtitle': 'Один вариант',
        'options': [
            _opt('store_opening', 'Открытие магазина', 'a retail store opening'),
            _opt('time_capsule', 'Закладка капсулы', 'a time capsule laying ceremony'),
            _opt('project_launch', 'Старт проекта или продаж', 'a project or sales launch'),
            _opt('product_presentation', 'Презентация продукта', 'a product presentation'),
            _opt('forum', 'Форум', 'a business forum'),
            _opt('summit', 'Саммит', 'a high-level summit'),
            _opt('conference', 'Конференция с билетами', 'a ticketed conference'),
            _opt('concert', 'Концерт с билетами', 'a ticketed concert'),
            _opt('fashion_show', 'Показ мод', 'a fashion show'),
            _opt('teambuilding', 'Тимбилдинг', 'a corporate teambuilding event'),
            _opt('strategy_session', 'Стратсессия', 'a strategy session'),
        ],
    },
    {
        'key': 'goals',
        'type': MULTI,
        'max_choices': 3,
        'title': 'Чего вы хотите добиться?',
        'subtitle': 'Выберите до 3 вариантов',
        'options': [
            _opt('sales', 'Больше продаж', 'drive more sales'),
            _opt('awareness', 'Чтобы о нас узнали', 'build brand awareness'),
            _opt('press', 'Статьи в СМИ', 'earn press coverage'),
            _opt('social', 'Чтобы разлетелось в соцсетях', 'go viral on social media'),
            _opt('partners', 'Новых партнёров', 'attract new partners'),
            _opt('trust', 'Больше доверия к бренду', 'deepen brand trust'),
            _opt('status', 'Выше статус компании', 'raise the company\'s status'),
            _opt('community', 'Своё комьюнити', 'grow an owned community'),
        ],
    },
    {
        'key': 'emotion',
        'type': SINGLE,
        'max_choices': 1,
        'title': 'Что должны чувствовать гости?',
        'subtitle': 'Одно главное',
        'options': [
            _opt('delight', 'Восторг', 'delight'),
            _opt('thrill', 'Азарт', 'thrill and excitement'),
            _opt('pride', 'Гордость', 'pride'),
            _opt('inspiration', 'Вдохновение', 'inspiration'),
            _opt('energy', 'Энергию', 'energy'),
            _opt('admiration', 'Восхищение', 'admiration'),
            _opt('trust', 'Доверие', 'trust'),
            _opt('joy', 'Радость', 'joy'),
        ],
    },
    {
        'key': 'brand_attributes',
        'type': MULTI,
        'max_choices': 3,
        'title': 'Каким люди должны увидеть ваш бренд?',
        'subtitle': 'Выберите до 3 вариантов',
        'options': [
            _opt('premium', 'Дорогой', 'premium and expensive'),
            _opt('modern', 'Современный', 'modern'),
            _opt('bold', 'Смелый', 'bold'),
            _opt('innovative', 'Инновационный', 'innovative'),
            _opt('reliable', 'Надёжный', 'reliable'),
            _opt('market_leader', 'Лидер рынка', 'a market leader'),
            _opt('national', 'Национальный', 'national in scope'),
            _opt('global', 'Мировой', 'global in scope'),
            _opt('youthful', 'Молодёжный', 'youthful'),
            _opt('eco', 'Экологичный', 'environmentally conscious'),
        ],
    },
    {
        'key': 'reference',
        'type': SINGLE,
        'max_choices': 1,
        'title': 'На что похоже ваше событие?',
        'subtitle': 'Один вариант',
        'options': [
            _opt('apple', 'Презентация Apple',
                 'an Apple keynote: minimal, precise, generous negative space'),
            _opt('formula1', 'Формула-1',
                 'Formula 1: speed, motion, high-contrast sponsor-grade graphics'),
            _opt('fashion_week', 'Неделя моды',
                 'fashion week: editorial, austere, high-fashion typography'),
            _opt('olympics', 'Олимпиада',
                 'the Olympics: monumental, ceremonial, national scale'),
            _opt('ted', 'TED',
                 'a TED talk: ideas-first, clean stage, warm accent colour'),
            _opt('red_bull', 'Red Bull',
                 'Red Bull: extreme, kinetic, adrenaline-driven'),
            _opt('netflix', 'Премьера Netflix',
                 'a Netflix premiere: cinematic, dark, dramatic key art'),
            _opt('festival', 'Фестиваль',
                 'a festival: vivid, crowded, celebratory'),
        ],
    },
    {
        'key': 'scale',
        'type': SINGLE,
        'max_choices': 1,
        'title': 'Насколько громким должно быть событие?',
        'subtitle': 'Один вариант',
        'options': [
            _opt('private', 'Только для своих гостей',
                 'intimate, invitation-only; restrained and confident tone'),
            _opt('city', 'Чтобы говорил весь город',
                 'city-wide buzz; energetic, public-facing tone'),
            _opt('national', 'Чтобы писали СМИ по всей стране',
                 'national press coverage; authoritative, headline-ready tone'),
            _opt('international', 'Международный уровень',
                 'international stature; global, ceremonial tone'),
        ],
    },
]

QUESTIONS_BY_KEY = {q['key']: q for q in QUESTIONS}


def options_by_value(key):
    return {opt['value']: opt for opt in QUESTIONS_BY_KEY[key]['options']}


def describe(key, value):
    """English hint for one chosen value, falling back to the raw value."""
    option = options_by_value(key).get(value)
    return option['hint'] if option else str(value)


def label(key, value):
    option = options_by_value(key).get(value)
    return option['label'] if option else str(value)
