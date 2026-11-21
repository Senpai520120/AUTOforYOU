"""Решение владельца 2026-11-20: гибрид (HEV) — по формуле ДВС, ставка по объёму (пп. 215.3.5-1 ПКУ)."""
from datetime import date
from decimal import Decimal as D

from pricing.models import CustomsExciseRate
from pricing.tests_config import SeededCase


class HybridExciseByVolumeTests(SeededCase):
    def _calc(self, cc):
        resp = self.calc(fuel_type='hybrid', engine_cc=cc)
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()

    def test_seed_splits_hybrid_by_3000(self):
        rows = CustomsExciseRate.objects.filter(fuel_type='hybrid').order_by('engine_cc_min')
        self.assertEqual([(r.engine_cc_min, r.engine_cc_max, r.eur_per_100cc) for r in rows],
                         [(0, 3000, D('5.0000')), (3001, None, D('10.0000'))])

    def test_hybrid_2500_uses_5_per_100cc(self):
        data = self._calc(2500)
        age = date.today().year - 2018  # PAYLOAD: 2018 г. → К вік
        self.assertEqual(D(data['applied_rates']['excise_eur_per_100cc']), D('5'))
        self.assertEqual(D(data['breakdown']['excise_eur']), D('5') * D('25') * age)

    def test_hybrid_3500_uses_10_per_100cc(self):
        data = self._calc(3500)
        age = date.today().year - 2018
        self.assertEqual(D(data['applied_rates']['excise_eur_per_100cc']), D('10'))
        self.assertEqual(D(data['breakdown']['excise_eur']), D('10') * D('35') * age)


class HybridSplitMigrationTests(SeededCase):
    """Старая БД: одна строка hybrid 0..∞ по 5 → делится; правленая админом остаётся."""

    def _split(self):
        import importlib

        from django.apps import apps
        importlib.import_module('pricing.migrations.0013_hybrid_excise_by_volume').split_hybrid(apps, None)

    def _make_old(self, eur='5.0000'):
        CustomsExciseRate.objects.filter(fuel_type='hybrid').delete()
        CustomsExciseRate.objects.create(fuel_type='hybrid', engine_cc_min=0, engine_cc_max=None,
                                         eur_per_100cc=D(eur), valid_from=date(2026, 1, 1))

    def test_untouched_old_row_is_split(self):
        self._make_old()
        self._split()
        rows = CustomsExciseRate.objects.filter(fuel_type='hybrid').order_by('engine_cc_min')
        self.assertEqual([(r.engine_cc_min, r.engine_cc_max, r.eur_per_100cc) for r in rows],
                         [(0, 3000, D('5.0000')), (3001, None, D('10.0000'))])

    def test_admin_edited_row_untouched(self):
        self._make_old(eur='6.0000')
        self._split()
        self.assertEqual(CustomsExciseRate.objects.filter(fuel_type='hybrid').count(), 1)
