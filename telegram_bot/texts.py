"""Реестр текстов Telegram-бота и постов канала (задача 5.4, 07-C2).

Дефолты живут здесь и только здесь: из них data-миграция заливает `BotText`, и они же
используются, если ключа в БД нет (миграцию откатили, строку удалили). Бот не падает.

Два вида текстов:
- `html` - уходят с parse_mode='HTML'. В админке разрешены только теги Telegram из белого
  списка (`ALLOWED_TAGS`), всё остальное - ошибка валидации. Значения плейсхолдеров
  подставляются экранированными (`formatting.esc`), поэтому данные из БД и от пользователей
  разметку не меняют.
- `plain` - подписи кнопок, описания команд, текст для сайта. Теги запрещены, экранирования нет.
"""
import logging
import re
import string
from dataclasses import dataclass
from html.parser import HTMLParser

from django.core.cache import cache

logger = logging.getLogger(__name__)

HTML = 'html'
PLAIN = 'plain'
ALLOWED_TAGS = ('b', 'i', 'u', 's', 'a', 'code', 'pre')
CACHE_PREFIX = 'bottext:'
CACHE_TTL = 300  # страховка для нескольких процессов; основной сброс - сигналы post_save/post_delete


@dataclass(frozen=True)
class TextDef:
    kind: str
    description: str
    default: str
    placeholders: tuple[str, ...] = ()


REGISTRY: dict[str, TextDef] = {
    'start': TextDef(
        HTML, 'Ответ на /start',
        'Ласкаво просимо до AUTOforYOU! 🚗\n\n'
        '/help — список команд\n'
        '/latest — останні оголошення\n'
        '/unlink — відв\'язати акаунт\n\n'
        'Щоб отримувати сповіщення — прив\'яжіть акаунт у особистому кабінеті.',
    ),
    'start_other_payload': TextDef(
        HTML, 'Ответ на /start с неизвестным параметром ссылки',
        'Ласкаво просимо до AUTOforYOU!\n'
        'Для прив\'язки акаунту скористайтесь кнопкою в особистому кабінеті.',
    ),
    'help': TextDef(
        HTML, 'Ответ на /help',
        '<b>Команди бота:</b>\n'
        '/start — привітання\n'
        '/help — ця довідка\n'
        '/latest — 3–5 свіжих оголошень (в наявності або в дорозі)\n'
        '/unlink — відв\'язати Telegram від акаунту',
    ),
    'latest_empty': TextDef(HTML, 'Ответ на /latest, когда объявлений нет', 'Наразі немає активних оголошень.'),
    'latest_item': TextDef(
        HTML, 'Карточка объявления в ответе на /latest',
        '🚗 <b>{title}</b>\n💵 {price} {currency}\n📦 {status}',
        ('title', 'price', 'currency', 'status'),
    ),
    'btn_view': TextDef(PLAIN, 'Кнопка под карточкой в /latest', 'Переглянути'),
    'link_ok': TextDef(
        HTML, 'Привязка выполнена',
        '✅ Акаунт успішно прив\'язано до Telegram! Тепер ви отримуватимете сповіщення.',
    ),
    'link_already': TextDef(HTML, 'Этот Telegram уже привязан к тому же аккаунту',
                            'ℹ️ Цей Telegram уже прив\'язано до вашого акаунту.'),
    'link_taken': TextDef(
        HTML, 'Этот Telegram уже привязан к другому аккаунту',
        '❌ Цей Telegram уже прив\'язано до іншого акаунту. '
        'Спочатку відв\'яжіть його там, потім повторіть спробу.',
    ),
    'link_expired': TextDef(
        HTML, 'Ссылка привязки просрочена, использована или заменена новой',
        '❌ Посилання застаріло або вже використане. Запросіть нове в особистому кабінеті.',
    ),
    'link_invalid': TextDef(HTML, 'Ссылка привязки не распознана', '❌ Невалідне посилання. Спробуйте ще раз.'),
    'unlink_ok': TextDef(
        HTML, 'Ответ на /unlink: отвязано',
        '✅ Telegram відв\'язано від акаунту. Сповіщення в Telegram більше не надходитимуть.',
    ),
    'unlink_not_linked': TextDef(HTML, 'Ответ на /unlink: аккаунт не привязан',
                                 'ℹ️ Цей Telegram не прив\'язано до жодного акаунту.'),
    'cmd_start': TextDef(PLAIN, 'Описание /start в меню команд (до 256 символов)', 'Привітання'),
    'cmd_help': TextDef(PLAIN, 'Описание /help в меню команд', 'Список команд'),
    'cmd_latest': TextDef(PLAIN, 'Описание /latest в меню команд', 'Останні оголошення'),
    'cmd_unlink': TextDef(PLAIN, 'Описание /unlink в меню команд', 'Відв\'язати акаунт'),
    'channel_listing': TextDef(
        HTML, 'Пост лота в канале',
        '🚗 <b>{title}</b>\n💵 {price} {currency}\n🔗 {url}',
        ('title', 'price', 'currency', 'url'),
    ),
    'channel_express_prefix': TextDef(
        HTML, 'Плашка перед постом срочного выкупа', '⚡ <b>ТЕРМІНОВИЙ ВИКУП</b>\n'),
    'btn_view_listing': TextDef(PLAIN, 'Кнопка под постом в канале', 'Переглянути оголошення'),
    'link_token_note': TextDef(
        PLAIN, 'Пояснение к ссылке привязки (ответ API, показывается на сайте)',
        'Перейдіть за посиланням у Telegram для прив\'язки акаунту. Діє {minutes} хвилин.',
        ('minutes',),
    ),
    # Напоминания о сроке объявления (Q9). Рассылку делает 4.3, здесь только тексты.
    'listing_expiring': TextDef(
        HTML, 'Напоминание: объявление скоро снимется',
        '⏳ Оголошення «{title}» буде знято з публікації через {days} дн. '
        'Продовжити безкоштовно: {renew_url}',
        ('title', 'days', 'renew_url'),
    ),
    'listing_expires_today': TextDef(
        HTML, 'Напоминание: объявление снимается сегодня',
        '⏳ Сьогодні закінчується строк оголошення «{title}». Продовжити безкоштовно: {renew_url}',
        ('title', 'renew_url'),
    ),
    'listing_expired': TextDef(
        HTML, 'Уведомление: объявление снято по сроку',
        'Оголошення «{title}» знято з публікації. Продовжити безкоштовно: {renew_url}',
        ('title', 'renew_url'),
    ),
}


# ─── Валидация ───────────────────────────────────────────────────────────────

_HREF_RE = re.compile(r'^https://[^\s{}"<>]+$')
_LANG_RE = re.compile(r'^language-[A-Za-z0-9_+-]{1,32}$')
_ENTITIES = ('lt', 'gt', 'amp', 'quot')


class _TagChecker(HTMLParser):
    """Проверка Telegram-HTML: теги из белого списка, парные, без голых `<`, `>`, `&`.

    Атрибуты: у `a` только `href` с литеральным https-адресом (без плейсхолдеров: адрес из данных
    пользователя - фишинг), у `pre`/`code` только `class="language-..."`. Комментарии, DOCTYPE,
    PI, CDATA и неподдерживаемые сущности запрещены.
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)  # иначе `&amp;` и голый `&` неразличимы
        self.stack: list[str] = []
        self.errors: list[str] = []

    def _check_attrs(self, tag, attrs):
        for name, value in attrs:
            if tag == 'a' and name == 'href':
                if not value or not _HREF_RE.match(value):
                    self.errors.append('ссылка <a href> должна быть литеральным адресом https:// '
                                       '(без плейсхолдеров, javascript: и tg://)')
            elif tag in ('pre', 'code') and name == 'class':
                if not value or not _LANG_RE.match(value):
                    self.errors.append(f'у <{tag}> допустим только class="language-..."')
            else:
                self.errors.append(f'атрибут {name} у тега <{tag}> не разрешён')

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f'тег <{tag}> не разрешён (разрешены: {", ".join(ALLOWED_TAGS)})')
            return
        if tag == 'a' and 'a' in self.stack:
            self.errors.append('тег <a> нельзя вкладывать в <a>')
        self._check_attrs(tag, attrs)
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.errors.append(f'самозакрывающийся тег <{tag}/> не поддерживается')

    def handle_endtag(self, tag):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f'тег </{tag}> не разрешён')
        elif not self.stack or self.stack[-1] != tag:
            self.errors.append(f'тег </{tag}> не имеет пары или закрыт не по порядку')
        else:
            self.stack.pop()

    def handle_data(self, data):
        if '<' in data or '>' in data or '&' in data:
            self.errors.append('символы <, > и & вне тегов нужно писать как &lt; &gt; &amp;')

    def handle_entityref(self, name):
        if name not in _ENTITIES:
            self.errors.append(f'сущность &{name}; не поддерживается (только &lt; &gt; &amp; &quot;)')

    def handle_charref(self, name):
        try:
            code = int(name[1:], 16) if name[:1] in ('x', 'X') else int(name)
        except ValueError:
            code = 0
        if code == 0 or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
            self.errors.append(f'числовая сущность &#{name}; недопустима')

    def handle_comment(self, data):
        self.errors.append('HTML-комментарии не поддерживаются')

    def handle_decl(self, decl):
        self.errors.append('объявления <!...> не поддерживаются')

    def handle_pi(self, data):
        self.errors.append('инструкции <?...> не поддерживаются')

    def unknown_decl(self, data):
        self.errors.append('блоки <![...]> не поддерживаются')


def validate_text(key: str, text: str) -> list[str]:
    """Список понятных ошибок; пустой - текст допустим."""
    definition = REGISTRY.get(key)
    if definition is None:
        return [f'неизвестный ключ «{key}»']
    errors: list[str] = []

    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as exc:
        return [f'ошибка в фигурных скобках: {exc}. Литеральную скобку пишите как {{{{ или }}}}']
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if field not in definition.placeholders:
            allowed = ', '.join('{%s}' % p for p in definition.placeholders) or 'нет'
            errors.append(f'плейсхолдер {{{field}}} не допускается (допустимые: {allowed})')
        elif spec or conversion:
            errors.append(f'в плейсхолдере {{{field}}} нельзя указывать формат или преобразование')

    if key.startswith('cmd_') and not 3 <= len(text) <= 256:
        errors.append('описание команды в меню Telegram: от 3 до 256 символов')
    if key.startswith('btn_') and len(text) > 64:
        errors.append('текст кнопки Telegram: не больше 64 символов')

    if definition.kind == PLAIN:
        if '<' in text or '>' in text:
            errors.append('в этом тексте HTML-теги не поддерживаются: уберите < и >')
    else:
        checker = _TagChecker()
        checker.feed(text)
        checker.close()
        errors.extend(checker.errors)
        if checker.stack:
            errors.append('не закрыт тег: ' + ', '.join(f'<{t}>' for t in checker.stack))
    return list(dict.fromkeys(errors))


# ─── Получение текста ────────────────────────────────────────────────────────

def _stored(key: str) -> str | None:
    """Текст из кэша или БД; None, если в БД ключа нет (отсутствие не кэшируем)."""
    cache_key = CACHE_PREFIX + key
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    from telegram_bot.models import BotText

    text = BotText.objects.filter(key=key).values_list('text', flat=True).first()
    if text is not None:
        cache.set(cache_key, text, CACHE_TTL)
    return text


def invalidate(key: str) -> None:
    cache.delete(CACHE_PREFIX + key)


def _render(template: str, definition: TextDef, ctx: dict) -> str:
    from telegram_bot.formatting import esc

    values = {k: (esc(v) if definition.kind == HTML else str(v)) for k, v in ctx.items()}
    return string.Formatter().vformat(template, (), values)


def get_text(key: str, **ctx) -> str:
    """Готовый текст по ключу. Значения `ctx` экранируются для html-текстов.

    Нет ключа в БД или сохранённый текст не рендерится (старый шаблон, лишний плейсхолдер) ->
    дефолт из реестра и предупреждение в лог; бот не падает.
    """
    definition = REGISTRY[key]  # неизвестный ключ - ошибка программиста
    template = None
    try:
        template = _stored(key)
    except Exception as exc:  # noqa: BLE001 - недоступная БД/кэш не должны ронять бота
        logger.warning('bottext %s: хранилище недоступно (%s), используется дефолт', key, type(exc).__name__)
    if template is None:
        logger.warning('bottext %s: нет в БД, используется дефолт', key)
        template = definition.default
    try:
        return _render(template, definition, ctx)
    except (KeyError, IndexError, ValueError, AttributeError):
        logger.warning('bottext %s: текст из БД не подходит к плейсхолдерам, используется дефолт', key)
        return _render(definition.default, definition, ctx)


async def aget_text(key: str, **ctx) -> str:
    """Для async-хендлеров: чтение БД/кэша идёт в потоке."""
    from asgiref.sync import sync_to_async

    return await sync_to_async(get_text)(key, **ctx)
