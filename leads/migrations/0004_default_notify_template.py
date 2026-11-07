from django.db import migrations

DEFAULT_TEMPLATE = (
    '🆕 <b>Нова заявка #{id}</b>\n'
    '👤 {name}\n'
    '📞 {phone} ({contact_method} {contact_handle})\n'
    '🚗 {car}\n'
    '💵 ≈ ${total_usd} / {total_uah} грн\n'
    '📍 Джерело: {source_details}\n'
    '💬 {comment}'
)


def create_default(apps, schema_editor):
    Settings = apps.get_model('leads', 'LeadNotificationSettings')
    Settings.objects.get_or_create(pk=1, defaults={'new_lead_template': DEFAULT_TEMPLATE})


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0003_lead_notify'),
    ]

    operations = [
        migrations.RunPython(create_default, migrations.RunPython.noop),
    ]
