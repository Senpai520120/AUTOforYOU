"""Права групп «Модератори»/«Адміністратори» на прокси очереди модерации (задача 1.11).

Миграция 0010 выдала права на local_listings.locallisting, но у прокси-модели
PendingLocalListingProxy (раздел «Черга модерації» в админке) свои content type и права,
поэтому модератор получал 403. Выдаём view/change (без add/delete).
"""
from django.db import migrations

MODERATORS = 'Модератори'
ADMINS = 'Адміністратори'
VERBOSE = 'Оголошення на модерації'   # verbose_name прокси; имена прав - как у Django
PERMS = {
    'view_pendinglocallistingproxy': f'Can view {VERBOSE}',
    'change_pendinglocallistingproxy': f'Can change {VERBOSE}',
}
CODENAMES = tuple(PERMS)


def grant(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    ct, _ = ContentType.objects.get_or_create(app_label='local_listings', model='pendinglocallistingproxy')
    perms = [
        Permission.objects.get_or_create(content_type=ct, codename=code, defaults={'name': name})[0]
        for code, name in PERMS.items()
    ]
    for name in (MODERATORS, ADMINS):
        group = Group.objects.filter(name=name).first()
        if group:
            group.permissions.add(*perms)


def revoke(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    perms = Permission.objects.filter(
        content_type__app_label='local_listings', codename__in=CODENAMES)
    for group in Group.objects.filter(name__in=(MODERATORS, ADMINS)):
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0015_customuser_session_version'),
        ('local_listings', '0007_alter_locallistingimage_image'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]
    operations = [migrations.RunPython(grant, revoke)]
