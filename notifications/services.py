from .models import Notification


def create_notification(user_id: int, ntype: str, title: str, text: str = '', link: str = '') -> Notification:
    """Create an in-app notification. Silently ignores unknown user_id."""
    return Notification.objects.create(
        user_id=user_id,
        type=ntype,
        title=title,
        text=text,
        link=link,
    )


def unread_count(user_id: int) -> int:
    return Notification.objects.filter(user_id=user_id, is_read=False).count()
