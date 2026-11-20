from decimal import Decimal

from django.db import migrations

# Решение владельца 2026-11-20, пп. 215.3.5-1 ПКУ: гибрид считается по формуле ДВС, ставка зависит от объёма.
# Меняем только нетронутую строку сида (hybrid, 0..∞, 5 EUR/100cc, без valid_to): правки админа не затираем.


def split_hybrid(apps, schema_editor):
    Rate = apps.get_model('pricing', 'CustomsExciseRate')
    if Rate.objects.filter(fuel_type='hybrid', engine_cc_min=3001).exists():
        return
    for row in Rate.objects.filter(fuel_type='hybrid', engine_cc_min=0, engine_cc_max__isnull=True,
                                   valid_to__isnull=True, eur_per_100cc=Decimal('5.0000')):
        Rate.objects.create(
            fuel_type='hybrid', engine_cc_min=3001, engine_cc_max=None, eur_per_100cc=Decimal('10.0000'),
            ev_excise_eur_per_kwh=row.ev_excise_eur_per_kwh, duty_rate=row.duty_rate, vat_rate=row.vat_rate,
            valid_from=row.valid_from)
        row.engine_cc_max = 3000
        row.save(update_fields=['engine_cc_max'])


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0012_place_names_uk'),
    ]

    operations = [
        migrations.RunPython(split_hybrid, migrations.RunPython.noop),
    ]
