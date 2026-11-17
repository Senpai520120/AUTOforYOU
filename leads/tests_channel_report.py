"""Отчёт пилота каналов (задача 9.57): счётчики по utm_source=tg_<канал> и активным объявлениям, без ПДн."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from leads.models import Lead
from local_listings.models import LocalListing
from tests.factories import make_lead, make_local_listing, make_region_city, make_user


def report(*args):
    out = StringIO()
    call_command('channel_report', *args, stdout=out)
    return out.getvalue()


class ChannelReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, cls.city = make_region_city()
        cls.owner = make_user()

    _n = 0

    def lead(self, source, **kw):
        ChannelReportTests._n += 1
        return make_lead(public_id=f'AFY-9999-{self._n:04d}', utm={'source': source, 'medium': 'partner'} if source else {}, **kw)

    def listing(self, channel, status=LocalListing.Status.ACTIVE):
        return make_local_listing(self.owner, status=status, region=self.region, city=self.city, source_channel=channel)

    def test_counts_leads_and_active_listings_per_channel(self):
        self.lead('tg_afy_news')
        self.lead('tg_afy_news')
        self.lead('tg_other_chan')
        self.listing('afy_news')
        self.listing('afy_news')
        text = report()
        self.assertIn('@afy_news: заявок 2, активных объявлений 2', text)
        self.assertIn('@other_chan: заявок 1, активных объявлений 0', text)

    def test_case_is_merged(self):
        self.lead('tg_AFY_News')
        self.lead('tg_afy_news')
        self.listing('Afy_News')
        self.assertIn('@afy_news: заявок 2, активных объявлений 1', report())

    def test_other_sources_do_not_count(self):
        self.lead('google')
        self.lead('')
        self.lead('tgx_chan')
        self.assertIn('Нет ни объявлений', report())

    def test_only_active_listings_count(self):
        self.listing('afy_news', status=LocalListing.Status.PENDING)
        self.listing('afy_news', status=LocalListing.Status.SOLD)
        self.assertIn('Нет ни объявлений', report())

    def test_window_excludes_old_leads(self):
        old = self.lead('tg_afy_news')
        Lead.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=15))
        self.listing('afy_news')
        self.assertIn('@afy_news: заявок 0, активных объявлений 1', report())
        self.assertIn('@afy_news: заявок 1,', report('--days', '30'))

    def test_report_has_no_personal_data(self):
        self.lead('tg_afy_news', name='Унікальне Імʼя', phone='+380509998877', email='unique@client-mail.test')
        self.listing('afy_news')
        text = report()
        for leaked in ('Унікальне', '380509998877', 'client-mail.test'):
            self.assertNotIn(leaked, text)

    def test_empty_database(self):
        self.assertIn('Нет ни объявлений', report())
