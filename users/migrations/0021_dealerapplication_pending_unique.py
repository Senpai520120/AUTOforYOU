"""D8 (1.17): не больше одной заявки дилера в статусе pending на пользователя.

Дубли pending по пользователю автоматически не сливаются (решение владельца): миграция
останавливается и выводит список.
"""
from collections import defaultdict

from django.db import migrations, models


def check_pending_duplicates(apps, schema_editor):
    Application = apps.get_model('users', 'DealerApplication')
    groups = defaultdict(list)
    for pk, user_id in Application.objects.filter(status='pending').order_by('pk').values_list('pk', 'user_id'):
        groups[user_id].append(pk)
    duplicates = {user_id: ids for user_id, ids in groups.items() if len(ids) > 1}
    if duplicates:
        lines = [f'  user_id={user_id}: заявки id={ids}' for user_id, ids in sorted(duplicates.items())]
        raise RuntimeError(
            'Миграция users.0021 остановлена: у пользователей несколько заявок дилера в статусе '
            'pending. Автоматически не сливаются, ничего не удалено и не изменено. Разрешите вручную '
            'в админке «Заявки дилеров»: переведите лишние pending-заявки (id указаны ниже) '
            'в статус rejected и повторите migrate:\n' + '\n'.join(lines)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0020_email_lowercase_unique'),
    ]

    operations = [
        migrations.RunPython(check_pending_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='dealerapplication',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status', 'pending')), fields=('user',),
                name='dealerapp_one_pending_per_user',
            ),
        ),
    ]
