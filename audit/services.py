"""Единая точка записи журнала аудита (1.13).

log_action пишет в текущей транзакции и ошибки не глотает: вызывающий оборачивает
действие и запись в transaction.atomic, сбой записи откатывает действие.
"""
import hashlib
import hmac

from django.conf import settings

from .models import AuditLog


def _ip_hash(request) -> str:
    if request is None:
        return ''
    from rest_framework.throttling import BaseThrottle
    # get_ident учитывает NUM_PROXIES (тот же IP, что у троттлинга); в журнал - только HMAC.
    ip = BaseThrottle().get_ident(request) or ''
    if not ip:
        return ''
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


def target_label(target) -> tuple[str, str, str]:
    """(target_type, target_id, target_repr) без ПДн: `customuser#45`, `locallisting#123`."""
    if target is None:
        return '', '', ''
    meta = target._meta
    return meta.label_lower, str(target.pk), f'{meta.model_name}#{target.pk}'


def _role_of(actor) -> str:
    if actor is None:
        return 'system'
    if actor.is_superuser:
        return 'superuser'
    return getattr(actor, 'role', '') or ''


def log_action(actor, action, target=None, *, reason='', before=None, after=None, request=None) -> AuditLog:
    target_type, target_id, target_repr = target_label(target)
    actor_obj = actor if getattr(actor, 'pk', None) else None
    return AuditLog.objects.create(
        actor=actor_obj,
        actor_id_snapshot=getattr(actor_obj, 'pk', None),
        actor_role_snapshot=_role_of(actor_obj),
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_repr=target_repr,
        reason=reason or '',
        before=before,
        after=after,
        ip_hash=_ip_hash(request),
    )
