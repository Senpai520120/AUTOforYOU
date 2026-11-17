import leads.models
from django.db import migrations, models

# Дефолтный текст из 0010: с именем, телефоном и email клиента. Заменяем только его (правки владельца не трогаем).
OLD_BODY = (
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
NEW_BODY = (
    'Нова заявка {id}\n\n'
    'Авто: {car}\n'
    'Підсумок: ≈ ${total_usd} / {total_uah} грн\n'
    'Спосіб звʼязку: {contact_method}\n'
    'Джерело: {source_details}\n\n'
    'Контакти клієнта — у заявці (потрібен вхід): {cabinet_url}\n'
    'Заявка в адмінці: {admin_url}\n'
)


def pii_free_default(apps, schema_editor):
    Settings = apps.get_model('leads', 'LeadNotificationSettings')
    for row in Settings.objects.filter(pk=1):
        # Админка могла сохранить переводы строк как CRLF: сравниваем без них.
        if row.email_body_template.replace('\r\n', '\n') == OLD_BODY:
            Settings.objects.filter(pk=row.pk).update(email_body_template=NEW_BODY)


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0010_default_email_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadnotificationsettings',
            name='email_always',
            field=models.BooleanField(default=False, help_text='Вимкнено: лист іде лише коли Telegram не доставив. Увімкнено: лист іде завжди, незалежно від Telegram. У листі немає імені, телефону, email, контакту в месенджері та коментаря клієнта: лише номер заявки, авто, сума і посилання в адмінку та кабінет. Якщо Telegram доставив, а лист не дійшов, повторно він не надсилається автоматично: помилка видна в заявці (адмінка).', verbose_name='Листа брокеру надсилати завжди'),
        ),
        migrations.AlterField(
            model_name='leadnotificationsettings',
            name='broker_emails',
            field=models.TextField(blank=True, help_text='По одній адресі в рядку. Лист іде, якщо Telegram не налаштовано чи не доставив (або завжди, якщо ввімкнено «Листа брокеру надсилати завжди»). Порожньо → BROKER_NOTIFY_EMAIL з .env', validators=[leads.models.validate_email_lines], verbose_name='Резервний email брокера'),
        ),
        migrations.AlterField(
            model_name='leadnotificationsettings',
            name='email_body_template',
            field=models.TextField(blank=True, help_text='Звичайний текст (без HTML), значення вставляються як є. Плейсхолдери як у шаблоні Telegram, але персональні поля ({name} {phone} {email} {contact_handle} {comment} {referrer} {page_url}) у листі завжди порожні.', validators=[leads.models.validate_template], verbose_name='Текст листа'),
        ),
        migrations.AlterField(
            model_name='leadnotificationsettings',
            name='email_subject_template',
            field=models.CharField(blank=True, help_text='Ті самі плейсхолдери, що й у шаблоні Telegram, але без HTML. Переноси рядків видаляються. У листі {name} {phone} {email} {contact_handle} {comment} {referrer} {page_url} завжди порожні.', max_length=200, validators=[leads.models.validate_template], verbose_name='Тема листа'),
        ),
        migrations.RunPython(pii_free_default, migrations.RunPython.noop),
    ]
