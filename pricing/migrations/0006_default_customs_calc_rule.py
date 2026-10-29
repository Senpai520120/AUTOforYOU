"""Правило растаможки по умолчанию (2.5, Q5): воспроизводит прежние формулы калькулятора.

valid_from = 2000-01-01, а не дата миграции: иначе расчёты на более раннюю дату (calculation_date)
получили бы 422 «нет правила», хотя раньше считались. Значения подтверждает брокер (LAUNCH_CHECKLIST).
Только создание записи, если правил ещё нет; существующие данные не меняются.
"""
from datetime import date

from django.db import migrations


def create_default(apps, schema_editor):
    rule_model = apps.get_model('pricing', 'CustomsCalcRule')
    if not rule_model.objects.exists():
        rule_model.objects.create(valid_from=date(2000, 1, 1))


class Migration(migrations.Migration):
    dependencies = [('pricing', '0005_customs_calc_rule_and_date_ranges')]
    operations = [migrations.RunPython(create_default, migrations.RunPython.noop)]
