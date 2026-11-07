"""Ошибки переписки (4.7): view переводит их в коды ответа, а не 500/403 «нет доступа»."""


class ContactsInTextError(ValueError):
    """ANTISPAM_MODE=hard: в тексте контакты. Ответ 400 {"text": [...]} (06-Q1)."""

    message = 'Повідомлення містить контактні дані (телефон, посилання, месенджер). Видаліть їх.'

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)


class ConversationClosed(PermissionError):
    """Объявление продано или снято: ответ в диалог закрыт (E5). Ответ 403 «Діалог закрито»."""


class RecipientDeleted(ValueError):
    """Собеседник удалил аккаунт (Q3). Ответ 400 «Користувач видалений»."""
