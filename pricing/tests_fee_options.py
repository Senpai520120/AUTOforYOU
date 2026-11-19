"""Задача 2.18: «clean» в справочнике формы и реальные buyer fee Copart из pricing/data/*.csv.

Ожидаемые суммы читаются из CSV тем же загрузчиком, что и сидер (pricing.fee_tables), а не вписываются руками.
"""
from decimal import Decimal as D

from rest_framework.test import APIClient

from pricing import fee_tables
from pricing.cache import invalidate_all
from pricing.models import AuctionFeeTier
from pricing.tests_correctness import SeededCase

RATES_URL = '/api/v1/pricing/rates/'
CENT = D('0.01')


def _csv_buyer_fee(price, member='public', payment='secured', title='clean', auction='copart') -> D:
    price = D(price)
    rows = [r for r in fee_tables.load_tier_rows()
            if (r['auction'], r['member_type'], r['payment_type'], r['title_type']) == (auction, member, payment, title)
            and r['bid_min'] <= price and (r['bid_max'] is None or price <= r['bid_max'])]
    assert len(rows) == 1, f'в CSV для цены {price} найдено {len(rows)} строк'
    row = rows[0]
    fee = row['fee_flat'] if row['fee_flat'] is not None else price * row['fee_percent']
    return fee.quantize(CENT)


def _csv_fixed(fee_type, title, auction='copart') -> D:
    rows = [r for r in fee_tables.load_fixed_rows()
            if (r['auction'], r['fee_type'], r['title_type']) == (auction, fee_type, title)]
    assert len(rows) == 1
    return rows[0]['amount'].quantize(CENT)


def _clean_boundary_price() -> str:
    """Нижняя граница второго диапазона clean/public/secured: цена ровно на стыке двух тиров."""
    rows = sorted((r for r in fee_tables.load_tier_rows()
                   if (r['auction'], r['member_type'], r['payment_type'], r['title_type'])
                   == ('copart', 'public', 'secured', 'clean')), key=lambda r: r['bid_min'])
    return str(rows[1]['bid_min'])


class TitleTypesOptionsTests(SeededCase):
    def _title_values(self):
        resp = APIClient().get(RATES_URL)
        self.assertEqual(resp.status_code, 200)
        options = resp.json()['options']
        return [o['value'] for o in options['title_types']], options['defaults']['title_type']

    def test_clean_listed_when_active_clean_tier_exists(self):
        values, _ = self._title_values()
        self.assertIn('clean', values)

    def test_clean_label_is_ukrainian(self):
        options = APIClient().get(RATES_URL).json()['options']
        self.assertEqual({o['value']: o['label'] for o in options['title_types']}['clean'], 'Чистий (clean)')

    def test_clean_absent_without_clean_tier(self):
        AuctionFeeTier.objects.filter(title_type='clean').delete()
        invalidate_all()
        values, default = self._title_values()
        self.assertNotIn('clean', values)
        self.assertIn(default, values)

    def test_unknown_title_type_is_400(self):
        resp = self.calc(title_type='platinum')
        self.assertEqual(resp.status_code, 400)


class CopartControlPricesTests(SeededCase):
    """Три контрольные цены (public, secured, clean): buyer fee калькулятора == строка CSV."""

    def _check(self, price):
        b = self.calc(member_type='public', payment_type='secured', title_type='clean',
                      auction_price_usd=price).json()['breakdown']
        self.assertEqual(D(b['auction_fee_buyer_usd']), _csv_buyer_fee(price))

    def test_price_1400(self):
        self._check('1400')

    def test_price_5840(self):
        self._check('5840')

    def test_price_on_range_boundary(self):
        self._check(_clean_boundary_price())

    def test_price_in_percent_range(self):
        self._check('20000')

    def test_5840_is_not_flat_six_percent(self):
        b = self.calc(member_type='public', payment_type='secured', title_type='clean',
                      auction_price_usd='5840').json()['breakdown']
        self.assertNotEqual(D(b['auction_fee_buyer_usd']), (D('5840') * D('0.06')).quantize(CENT))


class GateFeeByTitleTests(SeededCase):
    PUBLIC = {'member_type': 'public', 'payment_type': 'secured', 'auction_price_usd': '5000'}

    def _gate(self, title):
        b = self.calc(title_type=title, **self.PUBLIC).json()['breakdown']
        return D(b['auction_fee_gate_usd'])

    def test_clean_uses_gate_from_data(self):
        self.assertEqual(self._gate('clean'), _csv_fixed('gate', 'clean'))
        self.assertEqual(self._gate('clean'), D('79.00'))

    def test_salvage_uses_gate_from_data(self):
        self.assertEqual(self._gate('salvage'), _csv_fixed('gate', 'salvage'))
        self.assertEqual(self._gate('salvage'), D('95.00'))
