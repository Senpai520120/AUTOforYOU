from django.db import migrations


def create_singleton(apps, schema_editor):
    SiteSettings = apps.get_model('site_settings', 'SiteSettings')
    SiteSettings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ('site_settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_singleton, migrations.RunPython.noop),
    ]
