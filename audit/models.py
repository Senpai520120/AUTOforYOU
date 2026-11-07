"""Журнал аудита действий модераторов и администраторов (задача 1.13, Q10).

Только добавление: изменить или удалить запись нельзя ни через save()/delete(), ни через
queryset.update()/delete() менеджера `objects`. Единственный путь удаления — purge_audit_log
по сроку хранения (через `_base_manager`). ПДн (email, телефон, имя) в журнал не пишутся:
пользователь — через FK и числовой снимок id, `target_repr` — вида `customuser#45`.
"""
from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LISTING_APPROVE = 'listing.approve', 'Оголошення схвалено'
    LISTING_REJECT = 'listing.reject', 'Оголошення відхилено'
    LISTING_HIDE = 'listing.hide', 'Оголошення сховано'
    REPORT_DISMISS = 'report.dismiss', 'Скаргу відхилено'
    REPORT_REVIEW = 'report.review', 'Скаргу розглянуто'
    USER_BLOCK = 'user.block', 'Користувача заблоковано'
    USER_UNBLOCK = 'user.unblock', 'Користувача розблоковано'
    USER_ROLE_ASSIGN = 'user.role_assign', 'Роль призначено'
    USER_ROLE_REVOKE = 'user.role_revoke', 'Роль знято'
    SETTINGS_CHANGE = 'settings.change', 'Налаштування змінено'
    AUDIT_PURGE = 'audit.purge', 'Очищення журналу за терміном'


class ImmutableAuditLog(Exception):
    """Попытка изменить или удалить запись журнала аудита."""


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableAuditLog('Журнал аудиту не змінюється.')

    def delete(self):
        raise ImmutableAuditLog('Журнал аудиту не видаляється (лише purge_audit_log за терміном).')


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Час')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Автор',
    )
    actor_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True, verbose_name='ID автора (знімок)')
    actor_role_snapshot = models.CharField(max_length=20, blank=True, verbose_name='Роль автора (знімок)')
    action = models.CharField(max_length=40, choices=AuditAction.choices, db_index=True, verbose_name='Дія')
    target_type = models.CharField(max_length=60, blank=True, verbose_name="Тип об'єкта")
    target_id = models.CharField(max_length=64, blank=True, verbose_name="ID об'єкта")
    target_repr = models.CharField(max_length=80, blank=True, verbose_name="Об'єкт")
    reason = models.TextField(blank=True, verbose_name='Причина')
    before = models.JSONField(null=True, blank=True, verbose_name='До')
    after = models.JSONField(null=True, blank=True, verbose_name='Після')
    ip_hash = models.CharField(max_length=64, blank=True, verbose_name='Хеш IP')

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Запис журналу аудиту'
        verbose_name_plural = 'Журнал аудиту'
        indexes = [models.Index(fields=['target_type', 'target_id'], name='audit_target_idx')]

    def __str__(self):
        return f'{self.get_action_display()} {self.target_repr}'.strip()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ImmutableAuditLog('Журнал аудиту не змінюється.')
        kwargs['force_insert'] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableAuditLog('Журнал аудиту не видаляється (лише purge_audit_log за терміном).')
