"""Снимает самозваную роль admin: без is_superuser она прав не давала и не должна числиться."""
from django.db import migrations


def demote(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    qs = User.objects.filter(role='admin', is_superuser=False)
    qs.filter(is_verified_dealer=True).update(role='dealer')
    qs.update(role='buyer')


class Migration(migrations.Migration):
    dependencies = [('users', '0010_role_groups')]
    operations = [migrations.RunPython(demote, migrations.RunPython.noop)]
