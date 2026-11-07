from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models


def backfill_price_usd(apps, schema_editor):
    """Курс на дату миграции; без курса поле остаётся пустым (такие объявления вне фильтра по цене)."""
    LocalListing = apps.get_model('local_listings', 'LocalListing')
    ExchangeRate = apps.get_model('pricing', 'ExchangeRate')

    def latest(a, b):
        return ExchangeRate.objects.filter(from_currency=a, to_currency=b).order_by('-date').first()

    cents = Decimal('0.01')
    for cur in ('USD', 'UAH', 'EUR'):
        qs = LocalListing.objects.filter(currency=cur, price_usd__isnull=True)
        if cur == 'USD':
            for obj in qs.iterator():
                obj.price_usd = obj.price.quantize(cents)
                obj.save(update_fields=['price_usd'])
            continue
        direct, inverse = latest(cur, 'USD'), latest('USD', cur)
        for obj in qs.iterator():
            if direct and direct.rate:
                value = obj.price * direct.rate
            elif inverse and inverse.rate:
                value = obj.price / inverse.rate
            else:
                continue
            obj.price_usd = value.quantize(cents, rounding=ROUND_HALF_UP)
            obj.save(update_fields=['price_usd'])


class Migration(migrations.Migration):

    dependencies = [
        ('local_listings', '0008_listing_attribution'),
        ('pricing', '0009_uadeliveryrate_brokerservicefee'),
    ]

    operations = [
        migrations.AddField(
            model_name='locallisting',
            name='price_usd',
            field=models.DecimalField(
                blank=True, db_index=True, decimal_places=2, editable=False, max_digits=14, null=True,
                verbose_name='Ціна, USD (за курсом на момент збереження)',
            ),
        ),
        migrations.RunPython(backfill_price_usd, migrations.RunPython.noop),
    ]
