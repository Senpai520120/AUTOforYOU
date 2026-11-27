"""pricing/calculator.py: демо-флаги, справочники формы и доставка по Украине (scripts/mutation.sh calculator).

Тесты против выживших мутантов: демо-баннер включается только непроверенной ставкой или курсом из сида,
форма «настроена» только при всех справочниках, выбор доставки - по точному id и порту ЕС.
"""
from datetime import date, datetime
from datetime import timezone as dt_timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from pricing.calculator import (
    RateCatalog,
    SelectedRates,
    _uk_names,
    build_form_options,
    catalog_is_demo,
    exchange_rate_info,
    pick_ua_delivery,
    public_extra_options,
    rule_to_dict,
    selection_is_demo,
    ua_delivery_available,
)

ON = date(2026, 6, 1)
OLD = date(2026, 1, 1)


def _r(pk=1, verified=True, **kw):
    return SimpleNamespace(pk=pk, valid_from=OLD, valid_to=None, is_verified=verified, **kw)


def _rate(cur, source='nbu', pk=1):
    return SimpleNamespace(pk=pk, from_currency='USD', to_currency=cur, date=OLD, source=source)


class DemoFlagsTests(SimpleTestCase):
    def test_selection_demo_by_unverified_or_missing_flag(self):
        nbu = _rate('UAH')
        self.assertIs(selection_is_demo(SelectedRates(tier=_r(), usd_to_uah=nbu, usd_to_eur=nbu)), False)
        self.assertIs(selection_is_demo(SelectedRates(tier=_r(verified=False), usd_to_uah=nbu)), True)
        no_flag = SimpleNamespace(pk=1, valid_from=OLD)
        self.assertIs(selection_is_demo(SelectedRates(tier=no_flag, usd_to_uah=nbu)), True)

    def test_selection_demo_only_for_demo_source(self):
        for source, expected in (('nbu', False), ('manual', False), ('demo', True)):
            with self.subTest(source=source):
                sel = SelectedRates(tier=_r(), usd_to_uah=_rate('UAH', source), usd_to_eur=_rate('EUR'))
                self.assertIs(selection_is_demo(sel), expected)

    def test_catalog_demo(self):
        def catalog(verified=True, source='nbu'):
            return RateCatalog(auction_fee_tiers=[_r(verified=verified)],
                               exchange_rates=[_rate('UAH', source), _rate('EUR', 'nbu', pk=2)])
        self.assertIs(catalog_is_demo(catalog(), ON), False)
        self.assertIs(catalog_is_demo(catalog(source='manual'), ON), False)
        self.assertIs(catalog_is_demo(catalog(verified=False), ON), True)
        self.assertIs(catalog_is_demo(catalog(source='demo'), ON), True)
        no_flag = RateCatalog(auction_fee_tiers=[SimpleNamespace(pk=1, valid_from=OLD, valid_to=None)],
                              exchange_rates=[_rate('UAH'), _rate('EUR', pk=2)])
        self.assertIs(catalog_is_demo(no_flag, ON), True)

    def test_exchange_rate_source_and_freshness(self):
        nbu = SimpleNamespace(date=date(2026, 5, 29), source='nbu')
        demo = SimpleNamespace(date=date(2026, 5, 29), source='demo')
        info = exchange_rate_info(nbu, nbu, ON, max_age_days=10)
        self.assertEqual((info['exchange_rate_source'], info['exchange_rate_stale']), ('nbu', False))
        self.assertEqual(exchange_rate_info(nbu, demo, ON, max_age_days=10)['exchange_rate_source'], 'demo')


class RuleToDictTests(SimpleTestCase):
    def test_datetime_iso_and_missing_dates_none(self):
        rule = SimpleNamespace(pk=3, pension_bracket_base='a', pension_rate_base='b',
                               customs_value_includes_eu_to_ua=False, age_coeff_min=1, age_coeff_max=15,
                               age_offset_years=0, confirmed_by_broker=True,
                               confirmed_at=datetime(2026, 5, 1, 10, 30, tzinfo=dt_timezone.utc), valid_from=None)
        data = rule_to_dict(rule)
        self.assertEqual(data['confirmed_at'], '2026-05-01T10:30:00+00:00')
        self.assertIsNone(data['valid_from'])


class FormOptionsTests(SimpleTestCase):
    def test_uk_names_first_non_empty_wins(self):
        self.assertEqual(_uk_names(('', 'Без коду'), ('tx', ''), ('TX', 'Техас'), ('tx', 'Інше')), {'tx': 'Техас'})

    def _catalog(self, **drop):
        tiers = [_r(auction='copart', member_type='public', payment_type='card', title_type='clean'),
                 _r(pk=2, auction='copart', member_type='business', payment_type='wire', title_type='salvage')]
        full = dict(
            auction_fee_tiers=tiers,
            us_land_routes=[_r(auction_location='TX', auction_location_uk='', us_port='Houston', us_port_uk='')],
            ocean_freight=[_r(us_port='Houston', us_port_uk='', eu_port='Klaipeda', eu_port_uk='')],
            eu_to_ua=[_r(eu_port='Klaipeda')],
            excise_rates=[_r(fuel_type='petrol')],
            exchange_rates=[_rate('UAH'), _rate('EUR', pk=2)],
            customs_rules=[_r()],
            pension_brackets=[_r()],
        )
        for key in drop:
            full[key] = []
        return RateCatalog(**full)

    def test_configured_only_with_every_directory(self):
        self.assertIs(build_form_options(self._catalog(), ON, {})['is_configured'], True)
        for missing in ('auction_fee_tiers', 'ocean_freight', 'excise_rates', 'exchange_rates',
                        'customs_rules', 'pension_brackets'):
            with self.subTest(missing=missing):
                self.assertIs(build_form_options(self._catalog(**{missing: True}), ON, {})['is_configured'], False)

    def test_defaults_kept_if_known_else_first_value(self):
        opts = build_form_options(self._catalog(), ON, {'member_type': 'public', 'payment_type': 'cash'})
        self.assertEqual(opts['defaults'], {'member_type': 'public', 'payment_type': 'card', 'title_type': 'clean'})
        empty = build_form_options(self._catalog(auction_fee_tiers=True), ON, {'member_type': 'public'})
        self.assertEqual(empty['defaults'], {'member_type': None, 'payment_type': None, 'title_type': None})


class UaDeliveryTests(SimpleTestCase):
    def test_port_must_match_or_be_empty(self):
        rate = _r(eu_port='Klaipeda')
        self.assertIs(ua_delivery_available(rate, 'Klaipeda', ON), True)
        for other in ('Gdansk', 'Riga'):
            with self.subTest(other=other):
                self.assertIs(ua_delivery_available(rate, other, ON), False)
        self.assertIs(ua_delivery_available(_r(eu_port=''), 'Riga', ON), True)

    def test_pick_by_exact_id(self):
        rates = [_r(pk=1, eu_port=''), _r(pk=5, eu_port=''), _r(pk=9, eu_port='')]
        self.assertIs(pick_ua_delivery(rates, 5, 'Riga', ON), rates[1])
        self.assertIsNone(pick_ua_delivery(rates, 7, 'Riga', ON))

    def test_public_options_port_none_and_quote_flag(self):
        rates = [_r(pk=1, sort_order=1, destination='Київ', eu_port='', quote_on_request=False, cost_usd=100),
                 _r(pk=2, sort_order=2, destination='Львів', eu_port='Gdansk', quote_on_request=False, cost_usd=None),
                 _r(pk=3, sort_order=3, destination='Одеса', eu_port='', quote_on_request=True, cost_usd=50)]
        opts = public_extra_options(RateCatalog(ua_delivery_rates=rates), ON)['ua_delivery_rates']
        self.assertEqual([(o['eu_port'], o['quote_on_request']) for o in opts],
                         [(None, False), ('Gdansk', True), (None, True)])
