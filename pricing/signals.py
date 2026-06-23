from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    AuctionFeeTier, AuctionFixedFee, EuToUaDeliveryRate, ExchangeRate,
    CustomsExciseRate, OceanFreightRate, PensionFundBracket, UsLandRoute,
)
from .cache import invalidate


@receiver([post_save, post_delete], sender=AuctionFeeTier)
def _inv_tiers(sender, **kwargs):
    invalidate('tiers')


@receiver([post_save, post_delete], sender=AuctionFixedFee)
def _inv_fixed(sender, **kwargs):
    invalidate('fixed')


@receiver([post_save, post_delete], sender=UsLandRoute)
def _inv_land(sender, **kwargs):
    invalidate('us_land')


@receiver([post_save, post_delete], sender=OceanFreightRate)
def _inv_ocean(sender, **kwargs):
    invalidate('ocean')


@receiver([post_save, post_delete], sender=EuToUaDeliveryRate)
def _inv_eu_to_ua(sender, **kwargs):
    invalidate('eu_to_ua')


@receiver([post_save, post_delete], sender=ExchangeRate)
def _inv_exchange(sender, **kwargs):
    invalidate('exchange')


@receiver([post_save, post_delete], sender=CustomsExciseRate)
def _inv_excise(sender, **kwargs):
    invalidate('excise')


@receiver([post_save, post_delete], sender=PensionFundBracket)
def _inv_pension(sender, **kwargs):
    invalidate('pension')
