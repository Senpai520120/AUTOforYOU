"""Права групп «Брокери» и «Адміністратори» на заявки: просмотр и изменение, без удаления."""
from django.db import migrations

BROKERS = 'Брокери'
ADMINS = 'Адміністратори'  # модераторам права на заявки не выдаются
CODENAMES = ['view_lead', 'change_lead', 'view_leadstatuschange']


def grant(apps, schema_editor):
    from django.contrib.auth.management import create_permissions
    config = apps.get_app_config('leads')
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    perms = Permission.objects.filter(content_type__app_label='leads', codename__in=CODENAMES)
    for name in (BROKERS, ADMINS):
        Group.objects.get_or_create(name=name)[0].permissions.add(*perms)


def revoke(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for group in Group.objects.filter(name__in=[BROKERS, ADMINS]):
        group.permissions.remove(*Permission.objects.filter(
            content_type__app_label='leads', codename__in=CODENAMES))


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0001_initial'),
        ('users', '0010_role_groups'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [migrations.RunPython(grant, revoke)]
