"""Решение владельца 2026-11-20: брокер видит полную сумму {total_usd_full}, фолбэк на total_usd."""
import importlib
from decimal import Decimal

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from leads import notify
from leads.models import Lead, LeadNotificationSettings
from leads.tests_broker import LIST, BrokerBase


def _lead(snapshot, total='9000.50'):
    _lead.n = getattr(_lead, 'n', 0) + 1
    return Lead.objects.create(public_id=f'T-{_lead.n:05d}', name='Іван', phone='+380671234567', source='calculator', consent_at=timezone.now(), partner_consent_at=timezone.now(),
                               total_usd=Decimal(total), total_uah=Decimal('373520.75'),
                               calculation_snapshot=snapshot)


class NotifyTotalFullTests(TestCase):
    def test_full_sum_in_text(self):
        lead = _lead({'total_usd': '9000.50', 'total_usd_full': '13918.57'})
        self.assertEqual(notify.render_new_lead_text(lead, '{total_usd_full}'), '13 919')

    def test_old_snapshot_falls_back_to_total_usd(self):
        lead = _lead({'total_usd': '9000.50'})
        self.assertEqual(notify.render_new_lead_text(lead, '{total_usd_full}'), '9 000')

    def test_old_placeholder_still_works(self):
        lead = _lead({'total_usd_full': '13918.57'})
        self.assertEqual(notify.render_new_lead_text(lead, '{total_usd}'), '9 000')

    def test_fallback_email_has_full_sum_and_caption(self):
        lead = _lead({'total_usd_full': '13918.57'})
        text = notify.render_new_lead_text(lead, notify.FALLBACK_EMAIL_BODY)
        self.assertIn('≈ $13 919 (з розмитненням, орієнтовно)', text)

    def test_migration_updates_only_untouched_default(self):
        mig = importlib.import_module('leads.migrations.0014_total_usd_full_default')
        tg = importlib.import_module('leads.migrations.0004_default_notify_template').DEFAULT_TEMPLATE
        row = LeadNotificationSettings.get_solo()
        LeadNotificationSettings.objects.filter(pk=row.pk).update(new_lead_template=tg)
        mig.apply(apps, None)
        self.assertIn('{total_usd_full} (з розмитненням', LeadNotificationSettings.objects.get(pk=row.pk).new_lead_template)
        LeadNotificationSettings.objects.filter(pk=row.pk).update(new_lead_template=tg + ' моє')
        mig.apply(apps, None)
        self.assertEqual(LeadNotificationSettings.objects.get(pk=row.pk).new_lead_template, tg + ' моє')


class BrokerListTotalFullTests(BrokerBase):
    def test_list_has_full_sum_and_fallback(self):
        new = _lead({'total_usd_full': '13918.57'})
        old = _lead({'total_usd': '9000.50'})
        by_id = {r['id']: r for r in self.bc.get(LIST).data['results']}
        self.assertEqual(by_id[new.pk]['total_usd_full'], '13918.57')
        self.assertEqual(by_id[old.pk]['total_usd_full'], '9000.50')
