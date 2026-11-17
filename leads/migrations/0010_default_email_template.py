from django.db import migrations

# Только номер заявки: тема попадает в логи и превью почтовых клиентов, имени клиента там быть не должно.
DEFAULT_SUBJECT = 'Нова заявка {id}'
DEFAULT_BODY = (
    'Нова заявка {id}\n\n'
    'Імʼя: {name}\n'
    'Телефон: {phone}\n'
    'Email клієнта: {email}\n'
    'Спосіб звʼязку: {contact_method} {contact_handle}\n'
    'Авто: {car}\n'
    'Підсумок: ≈ ${total_usd} / {total_uah} грн\n'
    'Джерело: {source_details}\n'
    'Коментар: {comment}\n\n'
    'Заявка в адмінці: {admin_url}\n'
)


def set_defaults(apps, schema_editor):
    Settings = apps.get_model('leads', 'LeadNotificationSettings')
    obj, _ = Settings.objects.get_or_create(pk=1)
    # Правки владельца не перезаписываем: только пустые поля.
    if not obj.email_subject_template:
        obj.email_subject_template = DEFAULT_SUBJECT
    if not obj.email_body_template:
        obj.email_body_template = DEFAULT_BODY
    obj.save(update_fields=['email_subject_template', 'email_body_template'])


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0009_lead_email_delivery'),
    ]

    operations = [
        migrations.RunPython(set_defaults, migrations.RunPython.noop),
    ]
