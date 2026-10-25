from decimal import Decimal, InvalidOperation

from django.db.models import Case, F, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

# Межі, щоб завеликі числа давали 400, а не DataError (numeric overflow) на PostgreSQL.
_INT_LIMIT = 10**6
_DECIMAL_LIMIT = Decimal(10) ** 12


def _int(name, raw):
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise ValidationError({name: 'Потрібно ціле число.'}) from None
    if abs(value) >= _INT_LIMIT:
        raise ValidationError({name: 'Число поза допустимим діапазоном.'})
    return value


def _decimal(name, raw):
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError({name: 'Потрібно число.'}) from None
    if not value.is_finite():
        raise ValidationError({name: 'Потрібно число.'})
    if abs(value) >= _DECIMAL_LIMIT:
        raise ValidationError({name: 'Число поза допустимим діапазоном.'})
    return value


class LocalListingFilter(BaseFilterBackend):
    """Фільтри для місцевих оголошень (django-filter не потрібен — ручна реалізація)."""

    def filter_queryset(self, request, queryset, view):
        p = request.query_params

        make = p.get('make')
        model = p.get('model')
        fuel_type = p.get('fuel_type')
        transmission = p.get('transmission')
        body_type = p.get('body_type')
        region = p.get('region')
        city = p.get('city')
        mileage_max = p.get('mileage_max')
        search = p.get('search')
        ordering = p.get('ordering', '-created_at')

        if make:
            queryset = queryset.filter(make__icontains=make)
        if model:
            queryset = queryset.filter(model__icontains=model)
        # 05-Q4: нечисловое значение - 400, а не молчаливый пропуск или 500.
        # Цена (05-Q3) - всегда в USD: price_min/price_max и сортировка идут по price_usd (курс на момент сохранения).
        for name, field, lookup, parse in (
            ('year_min', 'year', 'gte', _int),
            ('year_max', 'year', 'lte', _int),
            ('price_min', 'price_usd', 'gte', _decimal),
            ('price_max', 'price_usd', 'lte', _decimal),
        ):
            raw = p.get(name)
            if raw:
                queryset = queryset.filter(**{f'{field}__{lookup}': parse(name, raw)})
        if fuel_type:
            queryset = queryset.filter(fuel_type=fuel_type)
        if transmission:
            queryset = queryset.filter(transmission=transmission)
        if body_type:
            queryset = queryset.filter(body_type=body_type)
        if region:
            try:
                queryset = queryset.filter(region_id=int(region))
            except (ValueError, TypeError):
                pass
        if city:
            try:
                queryset = queryset.filter(city_id=int(city))
            except (ValueError, TypeError):
                pass
        if mileage_max:
            try:
                queryset = queryset.filter(mileage_km__lte=int(mileage_max))
            except (ValueError, TypeError):
                pass
        if search:
            queryset = queryset.filter(
                Q(make__icontains=search) | Q(model__icontains=search) | Q(description__icontains=search)
            )

        # Annotate is_top: 1 if promoted_until is in the future, else 0
        now = timezone.now()
        queryset = queryset.annotate(
            _is_top=Case(
                When(promoted_until__gt=now, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

        # Priority: TOP → recently bumped → user-requested ordering
        allowed_orderings = {'created_at', '-created_at', 'price', '-price'}
        base_order = ordering if ordering in allowed_orderings else '-created_at'
        if base_order == 'price':
            base_order = F('price_usd').asc(nulls_last=True)  # по сумме в одной валюте (USD); без курса - в конец
        elif base_order == '-price':
            base_order = F('price_usd').desc(nulls_last=True)
        queryset = queryset.order_by(
            '-_is_top',
            F('bumped_at').desc(nulls_last=True),
            base_order,
        )

        return queryset
