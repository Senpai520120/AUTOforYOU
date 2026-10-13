"""Удаляет тестовые данные e2e (задача 0.4).

Трогает ТОЛЬКО пользователей @e2e.test (и каскадно их данные) и записи
с префиксом [E2E] / E2E. Работает только при E2E_SEED_ALLOWED=true.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from users.management.commands.e2e_seed import (
    E2E_CONTAINER_PREFIX, E2E_DOMAIN, E2E_PREFIX, E2E_VIN_PREFIX, require_e2e_allowed,
)


class Command(BaseCommand):
    help = 'Удаляет пользователей @e2e.test и записи с префиксом [E2E] (только E2E_SEED_ALLOWED=true).'

    def handle(self, *args, **options):
        require_e2e_allowed()
        from listings.models import Listing
        from local_listings.models import LocalListing
        from messaging.models import Conversation
        from shipments.models import Shipment
        from vehicles.models import Vehicle

        User = get_user_model()
        user_ids = list(User.objects.filter(email__iendswith=E2E_DOMAIN).values_list('pk', flat=True))

        def ids(model, cond):
            return list(model.objects.filter(cond).values_list('pk', flat=True).distinct())

        with transaction.atomic():
            # Порядок: зависимые записи раньше владельцев. PROTECT есть только на
            # region/city у LocalListing — справочники мы не удаляем.
            plan = (
                (Conversation, Q(initiator_id__in=user_ids) | Q(participants__in=user_ids)),
                (Listing, Q(seller_id__in=user_ids) | Q(vehicle__vin__startswith=E2E_VIN_PREFIX)),
                (Shipment, Q(container_no__startswith=E2E_CONTAINER_PREFIX)),
                (LocalListing, Q(owner_id__in=user_ids) | Q(description__startswith=E2E_PREFIX)),
                (Vehicle, Q(vin__startswith=E2E_VIN_PREFIX)),
                (User, Q(pk__in=user_ids)),
            )
            counts = {}
            for model, cond in plan:
                pks = ids(model, cond)
                model.objects.filter(pk__in=pks).delete()
                counts[model._meta.label] = len(pks)

        self.stdout.write('E2E cleanup: удалено')
        for label, n in counts.items():
            self.stdout.write(f'  {label}: {n}')
