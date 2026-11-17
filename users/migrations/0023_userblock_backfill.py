"""1.13: для уже забаненных (is_banned=True) создать UserBlock без автора.

Обратимо: откат удаляет только строки с этой причиной и без автора; флаги пользователей не трогает.
"""
from django.db import migrations

LEGACY_REASON = 'Заблоковано до впровадження журналу'


def backfill(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    UserBlock = apps.get_model('users', 'UserBlock')
    active = UserBlock.objects.filter(unblocked_at__isnull=True).values('user_id')
    UserBlock.objects.bulk_create(
        UserBlock(user_id=pk, reason=LEGACY_REASON, blocked_by=None)
        for pk in User.objects.filter(is_banned=True).exclude(pk__in=active).values_list('pk', flat=True)
    )


def unbackfill(apps, schema_editor):
    UserBlock = apps.get_model('users', 'UserBlock')
    UserBlock.objects.filter(reason=LEGACY_REASON, blocked_by__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0022_userblock'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
