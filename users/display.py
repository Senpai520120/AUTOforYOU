"""Публичное отображаемое имя пользователя (задача 1.9).

Никогда не производится от email или телефона: контрагент, покупатель,
отправитель сообщения и владелец объявления видят только это имя.
"""

ANONYMOUS_NAME = 'Користувач'
DELETED_NAME = 'Користувач видалений'


def public_display_name(user) -> str:
    """«Ім'я П.» (имя + первая буква фамилии); без имени — «Користувач»;
    для удалённого аккаунта — «Користувач видалений»."""
    if user is None or getattr(user, 'deleted_at', None) is not None:
        return DELETED_NAME
    # Только первое слово имени и инициал первого слова фамилии: в поля имени
    # нередко вводят ФИО целиком.
    first_words = (user.first_name or '').split()
    if not first_words:
        return ANONYMOUS_NAME
    last_words = (user.last_name or '').split()
    first = first_words[0]
    return f'{first} {last_words[0][0].upper()}.' if last_words else first
