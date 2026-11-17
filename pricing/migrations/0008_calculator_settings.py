"""Тексты калькулятора по умолчанию (2.6, 02-C1, 09-C6): одна запись pk=1, дальше правятся в админке."""
from django.db import migrations

from pricing.models import (
    DEFAULT_DEMO_BANNER_TEXT,
    DEFAULT_DEMO_BANNER_TITLE,
    DEFAULT_ESTIMATE_NOTE,
    DEFAULT_RESULT_WARNING,
)


def create_settings(apps, schema_editor):
    CalculatorSettings = apps.get_model('pricing', 'CalculatorSettings')
    CalculatorSettings.objects.get_or_create(pk=1, defaults={
        'result_warning': DEFAULT_RESULT_WARNING,
        'demo_banner_title': DEFAULT_DEMO_BANNER_TITLE,
        'demo_banner_text': DEFAULT_DEMO_BANNER_TEXT,
        'estimate_note': DEFAULT_ESTIMATE_NOTE,
    })


class Migration(migrations.Migration):
    dependencies = [('pricing', '0007_is_verified_source')]

    operations = [migrations.RunPython(create_settings, migrations.RunPython.noop)]
