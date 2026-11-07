"""Связать пользователя с учёткой Keycloak вручную (SSO-1).

Нужно для привилегированных (staff, superuser, broker, moderator, admin): их вход через SSO
по email не привязывается автоматически. `sub` взять в консоли Keycloak: Users → пользователь → ID.

    python manage.py link_oidc_user admin@example.com=0b6c...-uuid
    python manage.py link_oidc_user admin@example.com=<новый sub> --replace
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from users.models import OidcIdentity


class Command(BaseCommand):
    help = 'Связывает пользователя с учёткой Keycloak: <email>=<sub>. --replace меняет уже существующую связь.'

    def add_arguments(self, parser):
        parser.add_argument('pair', help='<email>=<sub>')
        parser.add_argument('--replace', action='store_true', help='Заменить связь пользователя или sub, если она уже есть')

    def handle(self, *args, pair, replace, **options):
        email, sep, sub = pair.partition('=')
        email, sub = email.strip(), sub.strip()
        if not sep or not email or not sub:
            raise CommandError('Формат: <email>=<sub>')
        try:
            user = get_user_model().objects.get(email__iexact=email)
        except get_user_model().DoesNotExist:
            raise CommandError(f'Нет пользователя {email}') from None
        except get_user_model().MultipleObjectsReturned:
            raise CommandError(f'Несколько пользователей с email {email} (разный регистр): свяжите вручную') from None

        with transaction.atomic():
            conflicts = list(
                OidcIdentity.objects.select_for_update().select_related('user').filter(Q(user=user) | Q(sub=sub))
            )
            if any(c.user_id == user.pk and c.sub == sub for c in conflicts):
                self.stdout.write(f'Уже связан: {user.email} = {sub}')
                return
            if conflicts and not replace:
                found = ', '.join(f'{c.user.email}={c.sub}' for c in conflicts)
                raise CommandError(f'Связь уже есть ({found}). Повторите с --replace, чтобы заменить.')
            for identity in conflicts:
                identity.delete()
            OidcIdentity.objects.create(user=user, sub=sub)
        self.stdout.write(self.style.SUCCESS(f'Связано: {user.email} = {sub}'))
