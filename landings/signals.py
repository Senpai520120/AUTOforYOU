from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ModelLandingPage
from .services import bump_cache_version


@receiver([post_save, post_delete], sender=ModelLandingPage)
def invalidate_landing_cache(sender, **kwargs):
    bump_cache_version()
