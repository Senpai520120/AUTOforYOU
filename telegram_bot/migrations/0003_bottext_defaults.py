from django.db import migrations

# Дефолтные тексты на момент миграции: копия, а не импорт живого реестра (позднейшие правки
# реестра не должны менять уже выполненную миграцию).
DEFAULTS = {
    'start': "Ласкаво просимо до AUTOforYOU! 🚗\n\n/help — список команд\n/latest — останні оголошення\n/unlink — відв'язати акаунт\n\nЩоб отримувати сповіщення — прив'яжіть акаунт у особистому кабінеті.",
    'start_other_payload': "Ласкаво просимо до AUTOforYOU!\nДля прив'язки акаунту скористайтесь кнопкою в особистому кабінеті.",
    'help': "<b>Команди бота:</b>\n/start — привітання\n/help — ця довідка\n/latest — 3–5 свіжих оголошень (в наявності або в дорозі)\n/unlink — відв'язати Telegram від акаунту",
    'latest_empty': 'Наразі немає активних оголошень.',
    'latest_item': '🚗 <b>{title}</b>\n💵 {price} {currency}\n📦 {status}',
    'btn_view': 'Переглянути',
    'link_ok': "✅ Акаунт успішно прив'язано до Telegram! Тепер ви отримуватимете сповіщення.",
    'link_already': "ℹ️ Цей Telegram уже прив'язано до вашого акаунту.",
    'link_taken': "❌ Цей Telegram уже прив'язано до іншого акаунту. Спочатку відв'яжіть його там, потім повторіть спробу.",
    'link_expired': '❌ Посилання застаріло або вже використане. Запросіть нове в особистому кабінеті.',
    'link_invalid': '❌ Невалідне посилання. Спробуйте ще раз.',
    'unlink_ok': "✅ Telegram відв'язано від акаунту. Сповіщення в Telegram більше не надходитимуть.",
    'unlink_not_linked': "ℹ️ Цей Telegram не прив'язано до жодного акаунту.",
    'cmd_start': 'Привітання',
    'cmd_help': 'Список команд',
    'cmd_latest': 'Останні оголошення',
    'cmd_unlink': "Відв'язати акаунт",
    'channel_listing': '🚗 <b>{title}</b>\n💵 {price} {currency}\n🔗 {url}',
    'channel_express_prefix': '⚡ <b>ТЕРМІНОВИЙ ВИКУП</b>\n',
    'btn_view_listing': 'Переглянути оголошення',
    'link_token_note': "Перейдіть за посиланням у Telegram для прив'язки акаунту. Діє {minutes} хвилин.",
    'listing_expiring': '⏳ Оголошення «{title}» буде знято з публікації через {days} дн. Продовжити безкоштовно: {renew_url}',
    'listing_expires_today': '⏳ Сьогодні закінчується строк оголошення «{title}». Продовжити безкоштовно: {renew_url}',
    'listing_expired': 'Оголошення «{title}» знято з публікації. Продовжити безкоштовно: {renew_url}',
}


def fill_defaults(apps, schema_editor):
    """Заливает дефолтные тексты; уже существующие (отредактированные) не трогает."""
    BotText = apps.get_model('telegram_bot', 'BotText')
    for key, text in DEFAULTS.items():
        BotText.objects.get_or_create(key=key, defaults={'text': text})


class Migration(migrations.Migration):
    dependencies = [('telegram_bot', '0002_bottext')]
    # Откат ничего не удаляет: отредактированные владельцем тексты не теряем (схему снимет 0002).
    operations = [migrations.RunPython(fill_defaults, migrations.RunPython.noop)]
