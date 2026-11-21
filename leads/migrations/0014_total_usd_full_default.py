import importlib

import leads.models
from django.db import migrations, models

# Решение владельца 2026-11-20: брокеру — полная сумма «з розмитненням, орієнтовно» ({total_usd_full}).
# Меняем только нетронутые дефолтные шаблоны (точное совпадение, без CRLF); правки админа не затираем.
OLD = 'Підсумок: ≈ ${total_usd} / {total_uah} грн'
NEW = 'Підсумок: ≈ ${total_usd_full} (з розмитненням, орієнтовно) / {total_uah} грн'
OLD_TG = '💵 ≈ ${total_usd} / {total_uah} грн'
NEW_TG = '💵 ≈ ${total_usd_full} (з розмитненням, орієнтовно) / {total_uah} грн'


def _norm(text):
    return text.replace('\r\n', '\n')


def apply(apps, schema_editor):
    tg_default = importlib.import_module('leads.migrations.0004_default_notify_template').DEFAULT_TEMPLATE
    body_default = importlib.import_module('leads.migrations.0011_email_always_pii_free').NEW_BODY
    Settings = apps.get_model('leads', 'LeadNotificationSettings')
    for row in Settings.objects.filter(pk=1):
        updates = {}
        if _norm(row.new_lead_template) == tg_default:
            updates['new_lead_template'] = tg_default.replace(OLD_TG, NEW_TG)
        if _norm(row.email_body_template) == body_default:
            updates['email_body_template'] = body_default.replace(OLD, NEW)
        if updates:
            Settings.objects.filter(pk=row.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0013_lead_backup_chat_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leadnotificationsettings',
            name='new_lead_template',
            field=models.TextField(blank=True, help_text='HTML Telegram (<b>, <i>). {total_usd_full} — повна сума з розмитненням (орієнтовно), {total_usd} — старий плейсхолдер (без розмитнення). Плейсхолдери: {id} {name} {phone} {email} {contact_method} {contact_handle} {car} {total_usd_full} {total_usd} {total_uah} {source} {source_details} {utm_source} {utm_medium} {utm_campaign} {utm_content} {referrer} {page_url} {comment} {admin_url} {cabinet_url}. Значення екрануються автоматично.', validators=[leads.models.validate_template], verbose_name='Шаблон повідомлення'),
        ),
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]
