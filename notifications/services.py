import logging
import re

from django.contrib.auth import get_user_model
from django.db import transaction

from .defaults import DEFAULT_TEMPLATES
from .models import Notification, NotificationTemplate

logger = logging.getLogger(__name__)


def create_notification(user_id: int, ntype: str, title: str, text: str = '', link: str = '') -> Notification:
    """Create an in-app notification."""
    return Notification.objects.create(
        user_id=user_id,
        type=ntype,
        title=title,
        text=text,
        link=link,
    )


def unread_count(user_id: int) -> int:
    return Notification.objects.filter(user_id=user_id, is_read=False).count()


_PLACEHOLDER = re.compile(r'\{([^{}]*)\}')


def _fill(template: str, context: dict) -> str:
    """Подстановка только известных {ключей}; без format_map (атрибуты и индексы из админки не исполняются)."""
    def sub(match):
        key = match.group(1)
        if key not in context:
            raise KeyError(key)
        return str(context[key])
    return _PLACEHOLDER.sub(sub, template)


def render_template(code: str, context: dict) -> tuple[str, str]:
    """(title, text) из NotificationTemplate; пустой или битый шаблон - запасной текст и ERROR в лог."""
    fallback = DEFAULT_TEMPLATES.get(code, ('Сповіщення', ''))
    tpl = NotificationTemplate.objects.filter(code=code).first()
    if tpl is not None and tpl.title.strip():
        try:
            return _fill(tpl.title, context), _fill(tpl.text, context)
        except KeyError:
            logger.error('notification template broken: code=%s', code)
    try:
        return _fill(fallback[0], context), _fill(fallback[1], context)
    except KeyError:
        logger.error('notification fallback broken: code=%s', code)
        return fallback[0], ''


def notify(user_id: int, ntype: str, context: dict, link: str = '') -> None:
    """Единая отправка уведомления (4.7, 06-Q5/06-Q7).

    In-app - в текущей транзакции; Telegram - после коммита (transaction.on_commit), иначе при откате
    действия сообщение уже ушло бы. Ошибки не роняют действие, но пишутся в лог (без текста и ПДн).
    Неактивному или обезличенному получателю уведомление не создаётся (Q3, E5).
    """
    user = get_user_model().objects.filter(pk=user_id, is_active=True, deleted_at__isnull=True).only('pk').first()
    if user is None:
        return
    title, text = render_template(ntype, context)
    try:
        with transaction.atomic():
            create_notification(user_id, ntype, title[:255], text, link[:500])
    except Exception:
        logger.exception('in-app notification failed: type=%s user=%s', ntype, user_id)

    def _send_telegram():
        try:
            from integrations.tasks import send_notification
            send_notification.delay(user_id, f'{title}\n{text}')
        except Exception:
            logger.exception('telegram notification failed: type=%s user=%s', ntype, user_id)

    transaction.on_commit(_send_telegram)
