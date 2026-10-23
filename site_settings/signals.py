from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PUBLIC_CACHE_KEY, SiteSettings


@receiver(post_save, sender=SiteSettings)
def invalidate_public_cache(sender, **kwargs):
    cache.delete(PUBLIC_CACHE_KEY)
