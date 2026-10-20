from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='listings.Listing')
def on_listing_created(sender, instance, created: bool, **kwargs) -> None:
    if not created:
        return
    from core.modules import module_enabled
    if not module_enabled('lots'):  # 2.8: лоты заморожены - в канал ничего не уходит (5.2 сохраняет проверку)
        return
    # Постим retail-листинги и все срочные выкупы (в т.ч. wholesale)
    if instance.channel != 'retail' and not instance.is_express_buyout:
        return
    if instance.channel != 'retail' and not module_enabled('b2b'):  # 2.8: wholesale не публикуется без B2B
        return
    from telegram_bot.tasks import post_listing_to_channel
    post_listing_to_channel.delay(instance.pk)
