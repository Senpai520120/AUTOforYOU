"""4.10: тексты бота для подтверждения телефона контактом. Обратимо: откат удаляет только неизменённые."""
from django.db import migrations

DEFAULTS = {
    'phone_ask': '📱 Щоб підтвердити телефон для подачі оголошень, натисніть «Поділитися контактом» нижче.',
    'btn_share_contact': 'Поділитися контактом',
    'phone_ok': '✅ Телефон підтверджено. Тепер можна подавати оголошення.',
    'phone_not_own': '❌ Потрібен ваш власний контакт: натисніть кнопку «Поділитися контактом», а не пересилайте чужий.',
    'phone_not_linked': "ℹ️ Спочатку прив'яжіть Telegram в особистому кабінеті на сайті, потім поділіться контактом.",
    'phone_taken': '❌ Цей номер уже підтверджено на іншому акаунті. Зверніться до підтримки.',
    'phone_bad': '❌ Не вдалося розпізнати номер. Спробуйте ще раз.',
}


def fill(apps, schema_editor):
    BotText = apps.get_model('telegram_bot', 'BotText')
    for key, text in DEFAULTS.items():
        BotText.objects.get_or_create(key=key, defaults={'text': text})


def unfill(apps, schema_editor):
    BotText = apps.get_model('telegram_bot', 'BotText')
    for key, text in DEFAULTS.items():
        BotText.objects.filter(key=key, text=text).delete()


class Migration(migrations.Migration):
    dependencies = [('telegram_bot', '0003_bottext_defaults')]
    operations = [migrations.RunPython(fill, unfill)]
