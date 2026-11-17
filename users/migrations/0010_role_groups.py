"""Группы ролей и их права (задача 1.2, Q10).

Брокери: просмотр pricing.Calculation (права на Lead появятся в 2.1/2.4).
Модератори и Адміністратори: local_listings.moderate_locallisting + view/change объявления (для админки).
Граница модератора: никаких payments.*, pricing.*, SiteSettings, Lead.
Email/ID пользователей здесь не фиксируются: роли назначаются в админке.
"""
from django.db import migrations

BROKERS = 'Брокери'
MODERATORS = 'Модератори'
ADMINS = 'Адміністратори'


def _ensure_permissions(apps):
    # Права создаются сигналом post_migrate, а он при чистой БД срабатывает
    # после всех миграций. Создаём нужные сами.
    from django.contrib.auth.management import create_permissions
    for label in ('local_listings', 'pricing'):
        try:
            config = apps.get_app_config(label)
        except LookupError:
            continue
        config.models_module = True  # create_permissions пропускает конфиги без models_module
        create_permissions(config, verbosity=0, apps=apps)


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    _ensure_permissions(apps)

    # Для работы в админке (очередь модерации, actions) нужны view/change объявления;
    # фото - только просмотр (inline). Тарифы, платежи, пользователи не выдаются.
    moderate = Permission.objects.filter(
        content_type__app_label='local_listings',
        codename__in=[
            'moderate_locallisting', 'view_locallisting', 'change_locallisting',
            'view_locallistingimage',
        ],
    )
    view_calc = Permission.objects.filter(
        content_type__app_label='pricing', codename='view_calculation',
    )
    Group.objects.get_or_create(name=BROKERS)[0].permissions.set(view_calc)
    Group.objects.get_or_create(name=MODERATORS)[0].permissions.set(moderate)
    Group.objects.get_or_create(name=ADMINS)[0].permissions.set(moderate)


def delete_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=[BROKERS, MODERATORS, ADMINS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_role_broker'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('local_listings', '0006_moderate_permission'),
        ('pricing', '0004_auction_fee_v2'),
    ]

    operations = [migrations.RunPython(create_groups, delete_groups)]
