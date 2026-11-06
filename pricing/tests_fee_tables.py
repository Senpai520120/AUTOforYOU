"""Сетки сборов аукционов из публичных страниц (задача 9.51): сбор по цене, title handling, CSV, сверка, давность.

Суммы в проверках взяты из страниц Copart/IAA (см. pricing/data/*.csv, колонка source_url), а не из самого CSV.
"""
from datetime import date, timedelta
from decimal import Decimal as D
from io import StringIO
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from pricing import fee_tables
from pricing.cache import invalidate_all
from pricing.calculator import (
    LandedCostBreakdown,
    calc_auction_fees,
    fees_freshness,
    lookup_fixed_fees,
)
from pricing.models import AuctionFeeTier, AuctionFixedFee, CalculatorSettings
from pricing.tests_correctness import PAYLOAD, SeededCase
from tests.base import CleanCacheTestCase

D0 = date(2026, 1, 1)


def _fee(pk, fee_type, title, amount, bid_min=None, bid_max=None, valid_from=D0, auction='copart'):
    return SimpleNamespace(pk=pk, auction=auction, fee_type=fee_type, title_type=title, amount=D(amount),
                           bid_min=None if bid_min is None else D(bid_min),
                           bid_max=None if bid_max is None else D(bid_max), valid_from=valid_from, valid_to=None)


VIRTUAL_BID = [
    _fee(1, 'virtual_bid', 'salvage', '0', '0', '99.99'),
    _fee(2, 'virtual_bid', 'salvage', '50', '100', '499.99'),
    _fee(3, 'virtual_bid', 'salvage', '65', '500', '999.99'),
    _fee(4, 'virtual_bid', 'salvage', '160', '8000', None),
]


class FixedFeeLookupPureTests(SimpleTestCase):
    def _vb(self, bid, fees=VIRTUAL_BID, title='salvage'):
        found = [f for f in lookup_fixed_fees(fees, 'copart', title, D0, D(bid)) if f.fee_type == 'virtual_bid']
        return [f.amount for f in found]

    def test_range_boundaries_are_inclusive_with_cents(self):
        self.assertEqual(self._vb('99.99'), [D('0')])
        self.assertEqual(self._vb('100.00'), [D('50')])

    def test_bid_with_cents_does_not_fall_between_tiers(self):
        self.assertEqual(self._vb('399.50'), [D('50')])

    def test_open_ended_range(self):
        self.assertEqual(self._vb('250000'), [D('160')])

    def test_ranged_fee_ignored_when_bid_unknown(self):
        fees = lookup_fixed_fees(VIRTUAL_BID, 'copart', 'salvage', D0)
        self.assertEqual(fees, [])

    def test_exact_title_beats_any(self):
        fees = [*VIRTUAL_BID, _fee(9, 'virtual_bid', 'any', '1', '100', '499.99')]
        self.assertEqual(self._vb('200', fees), [D('50')])

    def test_any_title_used_when_no_exact(self):
        fees = [_fee(9, 'virtual_bid', 'any', '1', '100', '499.99')]
        self.assertEqual(self._vb('200', fees, title='clean'), [D('1')])

    def test_fee_without_range_applies_to_any_bid(self):
        found = lookup_fixed_fees([_fee(1, 'gate', 'any', '105', auction='iaai')], 'iaai', 'salvage', D0, D('7'))
        self.assertEqual([f.amount for f in found], [D('105')])


class TitleHandlingPureTests(SimpleTestCase):
    TIER = SimpleNamespace(fee_flat=D('300'), fee_percent=None)

    def test_title_handling_is_separate_line_and_in_total(self):
        fees = [_fee(1, 'gate', 'any', '105', auction='iaai'), _fee(2, 'title_handling', 'any', '20', auction='iaai')]
        result = calc_auction_fees(D('5000'), self.TIER, fees)
        self.assertEqual((result.gate_fee, result.title_handling_fee, result.total), (D('105.00'), D('20.00'), D('425.00')))

    def test_no_title_handling_is_zero(self):
        result = calc_auction_fees(D('5000'), self.TIER, [])
        self.assertEqual((result.title_handling_fee, result.total), (D('0'), D('300.00')))

    def test_old_breakdown_dict_without_new_key_is_still_readable(self):
        """Расчёт, сохранённый до 9.51, не знает title handling: поле читается как 0, остальные не меняются."""
        old = {k: v for k, v in LandedCostBreakdown.__dataclass_fields__.items()}
        self.assertEqual(old['auction_fee_title_handling_usd'].default, D('0'))


class FreshnessPureTests(SimpleTestCase):
    def test_exactly_90_days_is_fresh(self):
        self.assertEqual(fees_freshness(date(2026, 8, 8), date(2026, 11, 6)),
                         {'fees_checked_on': '2026-08-08', 'fees_stale': False})

    def test_91_days_is_stale(self):
        self.assertEqual(fees_freshness(date(2026, 8, 7), date(2026, 11, 6)),
                         {'fees_checked_on': '2026-08-07', 'fees_stale': True})

    def test_no_date_makes_no_claim(self):
        self.assertEqual(fees_freshness(None, date(2026, 11, 6)), {'fees_checked_on': None, 'fees_stale': False})


# ─── Значения из CSV против страниц аукционов ────────────────────────────────

class SeededFeeValuesTests(SeededCase):
    def _tier(self, auction, member, pay, title, bid):
        from pricing.cache import get_auction_fee_tiers
        from pricing.calculator import lookup_tier
        return lookup_tier(get_auction_fee_tiers(), auction, D(bid), member, pay, title, date.today())

    def test_copart_non_clean_secured_flat(self):
        self.assertEqual(self._tier('copart', 'public', 'secured', 'salvage', '2500').fee_flat, D('610.00'))

    def test_copart_boundary_cents_not_lost(self):
        self.assertEqual(self._tier('copart', 'public', 'secured', 'salvage', '399.50').fee_flat, D('145.00'))
        self.assertEqual(self._tier('copart', 'public', 'secured', 'salvage', '400').fee_flat, D('175.00'))

    def test_copart_clean_differs_from_non_clean(self):
        self.assertEqual(self._tier('copart', 'public', 'secured', 'clean', '2500').fee_flat, D('500.00'))

    def test_copart_unsecured_percent_from_15000(self):
        self.assertEqual(self._tier('copart', 'public', 'unsecured', 'salvage', '20000').fee_percent, D('0.1250'))

    def test_copart_licensed_up_to_25_cars_uses_same_grid(self):
        self.assertEqual(self._tier('copart', 'licensed', 'secured', 'clean', '1000').fee_flat, D('325.00'))

    def test_iaai_public_merged_range(self):
        self.assertEqual(self._tier('iaai', 'public', 'secured', 'any', '9500').fee_flat, D('945.00'))
        self.assertEqual(self._tier('iaai', 'public', 'secured', 'any', '15000').fee_percent, D('0.0750'))

    def test_broker_copart_stays_baseline_without_source(self):
        tier = self._tier('copart', 'broker', 'secured', 'salvage', '5000')
        self.assertEqual((tier.source_url, tier.checked_at), ('', None))

    def test_sourced_rows_have_source_and_check_date(self):
        self.assertFalse(AuctionFeeTier.objects.filter(member_type='public').filter(source_url='').exists())
        self.assertFalse(AuctionFixedFee.objects.exclude(source_url='').filter(checked_at__isnull=True).exists())


class CalculateApiFeesTests(SeededCase):
    PUBLIC = {'member_type': 'public', 'auction_price_usd': '5000'}

    def test_copart_fees_breakdown_for_5000(self):
        b = self.calc(**self.PUBLIC).json()['breakdown']
        # buyer $775 (5000-5499.99 non-clean) + gate $95 + env $15 + live bid $125 (4000-5999.99)
        self.assertEqual((b['auction_fee_buyer_usd'], b['auction_fee_gate_usd'], b['auction_fee_environmental_usd'],
                          b['auction_fee_virtual_bid_usd'], b['auction_fee_title_handling_usd'], b['auction_fee_usd']),
                         ('775.00', '95.00', '15.00', '125.00', '0', '1010.00'))

    def test_iaai_has_title_handling_and_new_service_fee(self):
        b = self.calc(auction='iaai', **self.PUBLIC).json()['breakdown']
        # buyer $775 + service $105 + EH&S $15 (baseline) + internet bid $125 + title handling $20
        self.assertEqual((b['auction_fee_gate_usd'], b['auction_fee_title_handling_usd'], b['auction_fee_usd']),
                         ('105.00', '20.00', '1040.00'))

    def test_response_has_checked_date_and_exclusions(self):
        body = self.calc(**self.PUBLIC).json()
        self.assertEqual(body['fees_checked_on'], '2026-11-06')
        self.assertFalse(body['fees_stale'])
        self.assertEqual(body['exclusions'], ['Ремонт автомобіля', 'Сертифікація та постановка на облік',
                                              'Доставка по Україні', 'Комісія брокера'])

    def test_checked_date_is_saved_in_snapshot(self):
        from pricing.models import Calculation
        body = self.calc(**self.PUBLIC).json()
        snap = Calculation.objects.get(pk=body['calculation_id']).rates_snapshot
        self.assertEqual((snap['fees_checked_on'], snap['auction_fee_title_handling']), ('2026-11-06', '0'))

    def test_stale_after_90_days(self):
        old = date.today() - timedelta(days=91)
        AuctionFeeTier.objects.update(checked_at=old)
        AuctionFixedFee.objects.update(checked_at=old)
        invalidate_all()
        body = self.calc(**self.PUBLIC).json()
        self.assertEqual((body['fees_checked_on'], body['fees_stale']), (old.isoformat(), True))

    def test_broker_baseline_has_no_checked_date(self):
        body = self.calc().json()  # PAYLOAD: broker
        self.assertEqual((body['fees_checked_on'], body['fees_stale']), (None, False))

    def test_exclusions_text_is_editable(self):
        settings_row = CalculatorSettings.load()
        settings_row.exclusions_text = 'Растаможка не входит\n\n  Страховка  '
        settings_row.save()
        self.assertEqual(self.calc().json()['exclusions'], ['Растаможка не входит', 'Страховка'])

    def test_payload_constant_is_broker(self):
        self.assertEqual(PAYLOAD['member_type'], 'broker')


# ─── check_fee_tables и seed --update ────────────────────────────────────────

class CheckFeeTablesTests(SeededCase):
    def run_cmd(self, *args):
        out = StringIO()
        try:
            call_command('check_fee_tables', *args, stdout=out)
            code = 0
        except CommandError as exc:
            code = exc.returncode
        return code, out.getvalue()

    def test_fresh_seed_matches_csv(self):
        code, out = self.run_cmd()
        self.assertEqual(code, 0, out)
        self.assertIn('БД совпадает с CSV', out)

    def test_changed_amount_is_a_difference(self):
        tier = AuctionFeeTier.objects.get(auction='copart', member_type='public', payment_type='secured',
                                          title_type='salvage', bid_min=D('2500'))
        tier.fee_flat = D('600.00')
        tier.save()
        code, out = self.run_cmd()
        self.assertEqual(code, 1, out)
        self.assertIn('[missing] AuctionFeeTier', out)
        self.assertIn('[extra] AuctionFeeTier', out)

    def test_removed_fixed_fee_is_a_difference(self):
        AuctionFixedFee.objects.filter(auction='iaai', fee_type='title_handling').delete()
        code, out = self.run_cmd()
        self.assertEqual(code, 1, out)
        self.assertIn('title_handling', out)

    def test_extra_active_fee_in_csv_group_is_a_difference(self):
        AuctionFixedFee.objects.create(auction='copart', fee_type='virtual_bid', title_type='any', amount=D('99'),
                                       valid_from=date(2026, 1, 1))
        code, out = self.run_cmd()
        self.assertEqual(code, 1, out)
        self.assertIn('[extra] AuctionFixedFee', out)

    def test_baseline_group_edits_are_not_compared(self):
        AuctionFeeTier.objects.filter(member_type='broker').update(fee_flat=D('1.00'), fee_percent=None)
        code, out = self.run_cmd()
        self.assertEqual(code, 0, out)

    def test_old_csv_check_date_warns(self):
        code, out = self.run_cmd('--date', (date.today() + timedelta(days=120)).isoformat())
        self.assertEqual(code, 0, out)
        self.assertIn('пора перечитать страницы', out)

    def test_command_reads_nothing_from_network(self):
        # Предохранитель core/test_runner.py роняет тест при внешнем соединении; здесь просто нет записи в БД.
        before = AuctionFeeTier.objects.count()
        self.run_cmd()
        self.assertEqual(AuctionFeeTier.objects.count(), before)


class SeedUpdateTests(CleanCacheTestCase):
    def _old_baseline(self):
        """Состояние до 9.51: старые baseline-ставки (gate IAA $95, virtual bid Copart $99 без диапазона)."""
        AuctionFixedFee.objects.create(auction='iaai', fee_type='gate', title_type='any', amount=D('95'),
                                       valid_from=date(2026, 1, 1))
        AuctionFixedFee.objects.create(auction='copart', fee_type='virtual_bid', title_type='any', amount=D('99'),
                                       valid_from=date(2026, 1, 1))
        AuctionFeeTier.objects.create(auction='copart', member_type='public', payment_type='secured',
                                      title_type='salvage', bid_min=D('0'), bid_max=D('399'), fee_flat=D('75'),
                                      valid_from=date(2026, 1, 1))

    def test_update_closes_old_creates_new_and_deletes_nothing(self):
        self._old_baseline()
        call_command('seed_auction_fees', '--update', verbosity=0, stdout=StringIO())
        old_gate = AuctionFixedFee.objects.get(auction='iaai', fee_type='gate', amount=D('95'))
        self.assertEqual(old_gate.valid_to, date(2026, 9, 30))  # день до 01.10.2026
        self.assertEqual(AuctionFixedFee.objects.get(auction='iaai', fee_type='gate', valid_to__isnull=True).amount,
                         D('105.00'))
        self.assertEqual(AuctionFeeTier.objects.get(bid_max=D('399'), fee_flat=D('75')).valid_to, date(2026, 11, 5))
        self.assertEqual(fee_tables.compare_with_db(date(2026, 11, 6)), [])

    def test_update_is_idempotent(self):
        call_command('seed_auction_fees', '--update', verbosity=0, stdout=StringIO())
        count = (AuctionFeeTier.objects.count(), AuctionFixedFee.objects.count())
        result = fee_tables.apply_csv()
        self.assertEqual((result['tiers_closed'], result['tiers_created'], result['fixed_closed'],
                          result['fixed_created']), (0, 0, 0, 0))
        self.assertEqual((AuctionFeeTier.objects.count(), AuctionFixedFee.objects.count()), count)

    def test_update_leaves_baseline_groups_alone(self):
        AuctionFeeTier.objects.create(auction='copart', member_type='broker', payment_type='secured',
                                      title_type='any', bid_min=D('0'), fee_flat=D('100'), valid_from=date(2026, 1, 1))
        call_command('seed_auction_fees', '--update', verbosity=0, stdout=StringIO())
        self.assertTrue(AuctionFeeTier.objects.get(member_type='broker', fee_flat=D('100')).valid_to is None)


class FixedFeeModelValidationTests(CleanCacheTestCase):
    def _fee(self, bid_min, bid_max, **kw):
        return AuctionFixedFee(auction='copart', fee_type='virtual_bid', title_type='salvage', amount=D('50'),
                               bid_min=None if bid_min is None else D(bid_min),
                               bid_max=None if bid_max is None else D(bid_max), valid_from=date(2026, 1, 1), **kw)

    def setUp(self):
        self._fee('100', '499.99').save()

    def test_adjacent_ranges_are_allowed(self):
        self._fee('500', '999.99').full_clean()

    def test_overlapping_ranges_are_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'Збір перетинається'):
            self._fee('400', '600').full_clean()

    def test_fee_without_range_overlaps_ranged_fee(self):
        with self.assertRaisesMessage(ValidationError, 'Збір перетинається'):
            self._fee(None, None).full_clean()

    def test_upper_bound_without_lower_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'Задайте «Ставка від»'):
            self._fee(None, '50').full_clean()

    def test_inverted_range_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'Верхня межа'):
            self._fee('900', '800').full_clean()
