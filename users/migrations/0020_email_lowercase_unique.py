"""D2 (1.17): email хранится в нижнем регистре, один аккаунт на адрес независимо от регистра.

Дубли по lower(email) автоматически не сливаются (решение владельца): миграция останавливается
и выводит список адресов и id - какой аккаунт оставить, решает человек.
"""
from collections import defaultdict

from django.db import migrations, models
from django.db.models.functions import Lower


def lowercase_emails(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    groups = defaultdict(list)
    for pk, email in User.objects.order_by('pk').values_list('pk', 'email'):
        groups[email.lower()].append((pk, email))
    duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}
    if duplicates:
        lines = [
            f'  {key}: ' + ', '.join(f'id={pk} ({email})' for pk, email in rows)
            for key, rows in sorted(duplicates.items())
        ]
        raise RuntimeError(
            'Миграция users.0020 остановлена: найдены аккаунты, email которых отличается только '
            'регистром. Автоматически не сливаются, ничего не удалено и не изменено. Разрешите вручную '
            'в админке: смените email одного из аккаунтов в каждой группе (id указаны ниже) '
            'и повторите migrate:\n' + '\n'.join(lines)
        )
    for pk, email in User.objects.exclude(email=Lower('email')).values_list('pk', 'email'):
        User.objects.filter(pk=pk).update(email=email.lower())


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0019_oidcidentity'),
    ]

    operations = [
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='customuser',
            constraint=models.UniqueConstraint(Lower('email'), name='users_customuser_email_lower_uniq'),
        ),
    ]
