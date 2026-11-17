"""Задача 1.15 (F3): уже завершённые платежи считаются применёнными, иначе повторный callback применил бы их снова.

Поле updated_at у Payment есть (auto_now): момент последней смены статуса на completed берём из него.
Обратная операция - noop: данные не удаляются, поле уберёт откат 0004.
"""
from django.db import migrations
from django.db.models import F


def backfill(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Payment.objects.filter(status='completed', applied_at__isnull=True).update(applied_at=F('updated_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_payment_applied_at'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
