from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FAQ_CACHE_KEY, FAQ_PLACES, HOW_IT_WORKS_CACHE_KEY, FaqItem, ImportStep


@receiver([post_save, post_delete], sender=ImportStep)
@receiver([post_save, post_delete], sender=FaqItem)
def invalidate_content_cache(sender, **kwargs):
    cache.delete_many([HOW_IT_WORKS_CACHE_KEY, *(FAQ_CACHE_KEY.format(place=p) for p in FAQ_PLACES)])
