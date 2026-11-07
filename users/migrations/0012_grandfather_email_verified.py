"""Q12: существующие аккаунты считаются подтвердившими email (иначе у них пропадут функции)."""
from django.db import migrations


def grandfather(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    User.objects.filter(is_email_verified=False).update(is_email_verified=True)


class Migration(migrations.Migration):
    dependencies = [('users', '0011_demote_bare_admin_role')]
    operations = [migrations.RunPython(grandfather, migrations.RunPython.noop)]
