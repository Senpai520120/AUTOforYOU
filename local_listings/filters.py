from django.db.models import Q, Case, When, Value, IntegerField, F
from django.utils import timezone
from rest_framework.filters import BaseFilterBackend


class LocalListingFilter(BaseFilterBackend):
    """Фільтри для місцевих оголошень (django-filter не потрібен — ручна реалізація)."""

    def filter_queryset(self, request, queryset, view):
        p = request.query_params

        make = p.get('make')
        model = p.get('model')
        year_min = p.get('year_min')
        year_max = p.get('year_max')
        price_min = p.get('price_min')
        price_max = p.get('price_max')
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
        if year_min:
            try:
                queryset = queryset.filter(year__gte=int(year_min))
            except (ValueError, TypeError):
                pass
        if year_max:
            try:
                queryset = queryset.filter(year__lte=int(year_max))
            except (ValueError, TypeError):
                pass
        if price_min:
            try:
                queryset = queryset.filter(price__gte=price_min)
            except (ValueError, TypeError):
                pass
        if price_max:
            try:
                queryset = queryset.filter(price__lte=price_max)
            except (ValueError, TypeError):
                pass
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
        queryset = queryset.order_by(
            '-_is_top',
            F('bumped_at').desc(nulls_last=True),
            base_order,
        )

        return queryset
