"""4.7 (06-C5): начальные тексты уведомлений. Обратимо: откат удаляет только неизменённые шаблоны."""
from django.db import migrations

TEMPLATES = {
    'new_message': ('Нове повідомлення від {sender}', '{listing}: «{preview}»'),
    'deal_proposed': (
        'Пропозиція угоди',
        'Продавець {sender} пропонує підтвердити угоду за оголошенням {listing}.',
    ),
    'deal_confirmed': ('Угоду підтверджено', 'Покупець підтвердив угоду за оголошенням {listing}.'),
    'deal_cancelled': ('Угоду скасовано', 'Учасник скасував угоду за оголошенням {listing}.'),
    'review_received': ('Новий відгук', 'Покупець залишив відгук {rating}★ про вас.'),
}


def seed(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    for code, (title, text) in TEMPLATES.items():
        NotificationTemplate.objects.get_or_create(code=code, defaults={'title': title, 'text': text})


def unseed(apps, schema_editor):
    NotificationTemplate = apps.get_model('notifications', 'NotificationTemplate')
    for code, (title, text) in TEMPLATES.items():
        NotificationTemplate.objects.filter(code=code, title=title, text=text).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0005_notificationtemplate_index'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
