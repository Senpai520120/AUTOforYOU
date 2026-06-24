from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='listings.Listing')
def on_listing_created(sender, instance, created: bool, **kwargs) -> None:
    if not created:
        return
    # Постим retail-листинги и все срочные выкупы (в т.ч. wholesale)
    if instance.channel != 'retail' and not instance.is_express_buyout:
        return
    from telegram_bot.tasks import post_listing_to_channel
    post_listing_to_channel.delay(instance.pk)
