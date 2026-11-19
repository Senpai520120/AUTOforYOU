from rest_framework import serializers

from content.models import has_draft_marker

from .models import ModelLandingPage

DEFAULT_H1 = 'Пригон {title} з США — ціна під ключ'

# В публичный ответ не попадают сетка ставок и id тарифов (rates_snapshot) - они остаются в снимке заявки.
CALCULATION_FIELDS = (
    'is_estimate', 'is_demo', 'rules_confirmed', 'rates_valid_from', 'rates_date', 'fees_checked_on', 'fees_stale', 'exclusions', 'currency', 'local_currency',
    'usd_to_uah', 'exchange_rate_date', 'total_usd', 'total_usd_full', 'total_uah', 'breakdown', 'applied_rates', 'inputs',
)


def landing_h1(page: ModelLandingPage) -> str:
    return page.h1 or DEFAULT_H1.format(title=page.title)


class LandingListSerializer(serializers.Serializer):
    """Элемент списка: slug, марка, модель, итог, updated_at. calc - готовый расчёт страницы."""

    def to_representation(self, pair):
        page, calc = pair
        return {
            'slug': page.slug, 'make': page.make, 'model': page.model,
            'total_usd': calc['total_usd'], 'total_usd_full': calc.get('total_usd_full') or calc['total_usd'], 'total_uah': calc['total_uah'],
            'updated_at': page.updated_at,
        }


class LandingDetailSerializer(serializers.Serializer):
    def to_representation(self, pair):
        page, calc = pair
        data = {
            'slug': page.slug, 'make': page.make, 'model': page.model,
            'year_from': page.year_from, 'year_to': page.year_to,
            'h1': landing_h1(page), 'intro': page.intro, 'description': page.description,
            'included_text': page.included_text, 'typical_term_text': page.typical_term_text,
            'meta_title': page.meta_title, 'meta_description': page.meta_description,
            'updated_at': serializers.DateTimeField().to_representation(page.updated_at),
            'calculation': {k: calc.get(k, calc['total_usd'] if k == 'total_usd_full' else None) for k in CALCULATION_FIELDS},
        }
        # Пустое не отдаём: ключа нет.
        if page.fuel_type:
            data['fuel_type'] = page.get_fuel_type_display()
        if page.engine_cc:
            data['engine_cc'] = page.engine_cc
        if page.battery_capacity_kwh:
            data['battery_capacity_kwh'] = str(page.battery_capacity_kwh)
        if page.generation:
            data['generation'] = page.generation
        faq = [{'question': i.question, 'answer': i.answer} for i in page.faq_items.filter(is_active=True)
               if not has_draft_marker(i.question, i.answer)]
        if faq:
            data['faq'] = faq
        return data
