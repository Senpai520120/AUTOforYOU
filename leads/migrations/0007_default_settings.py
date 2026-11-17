"""Singleton настроек журнала (3 из 4, 8000 USD, 12 мес.), окно атрибуции старых заявок, права групп."""
import calendar

from django.db import migrations

BROKERS = 'Брокери'
ADMINS = 'Адміністратори'
ADMIN_PERMS = ['view_funnel', 'view_leadpartnerstatuschange', 'view_leadexportlog']
BROKER_NO_DELETE = ['delete_lead', 'delete_leadstatuschange', 'delete_leadpartnerstatuschange']
MONTHS = 12


def add_months(dt, months):
    month_index = dt.month - 1 + months
    year, month = dt.year + month_index // 12, month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def forward(apps, schema_editor):
    from django.contrib.auth.management import create_permissions
    config = apps.get_app_config('leads')
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)

    apps.get_model('leads', 'LeadJournalSettings').objects.get_or_create(pk=1)
    Lead = apps.get_model('leads', 'Lead')
    for lead in Lead.objects.filter(attribution_until__isnull=True).only('pk', 'created_at'):
        Lead.objects.filter(pk=lead.pk).update(attribution_until=add_months(lead.created_at, MONTHS))

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    perms = Permission.objects.filter(content_type__app_label='leads', codename__in=ADMIN_PERMS)
    Group.objects.get_or_create(name=ADMINS)[0].permissions.add(*perms)
    broker = Group.objects.get_or_create(name=BROKERS)[0]
    broker.permissions.remove(*Permission.objects.filter(
        content_type__app_label='leads', codename__in=BROKER_NO_DELETE))


def backward(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    perms = Permission.objects.filter(content_type__app_label='leads', codename__in=ADMIN_PERMS)
    Group.objects.get_or_create(name=ADMINS)[0].permissions.remove(*perms)


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0006_journal_attribution'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [migrations.RunPython(forward, backward)]
