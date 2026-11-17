"""Журнал аудита (1.13): запись, неизменяемость, срок хранения, доступ только admin."""
from datetime import timedelta

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_admin_role, make_moderator, make_staff, make_user

from .models import AuditAction, AuditLog, ImmutableAuditLog
from .services import log_action
from .tasks import purge_audit_log

AUDIT_URL = '/admin/audit/auditlog/'


class TestLogAction(TestCase):

    def test_creates_row_with_before_after_and_snapshots(self):
        actor = make_admin_role()
        target = make_user()
        row = log_action(actor, AuditAction.USER_BLOCK, target, reason='Спам',
                         before={'is_banned': False}, after={'is_banned': True})
        row.refresh_from_db()
        self.assertEqual(row.actor, actor)
        self.assertEqual(row.actor_id_snapshot, actor.pk)
        self.assertEqual(row.actor_role_snapshot, 'admin')
        self.assertEqual(row.target_type, 'users.customuser')
        self.assertEqual(row.target_id, str(target.pk))
        self.assertEqual(row.target_repr, f'customuser#{target.pk}')
        self.assertEqual(row.before, {'is_banned': False})
        self.assertEqual(row.after, {'is_banned': True})
        self.assertEqual(row.ip_hash, '')  # вне запроса

    def test_request_ip_is_hashed_not_stored(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', REMOTE_ADDR='203.0.113.7')
        row = log_action(None, AuditAction.SETTINGS_CHANGE, request=request)
        self.assertEqual(len(row.ip_hash), 64)
        self.assertNotIn('203.0.113.7', row.ip_hash)
        self.assertEqual(row.actor_role_snapshot, 'system')

    def test_same_transaction_rollback_removes_row(self):
        with self.assertRaisesMessage(RuntimeError, 'boom'):
            with transaction.atomic():
                log_action(None, AuditAction.SETTINGS_CHANGE)
                raise RuntimeError('boom')
        self.assertFalse(AuditLog.objects.exists())

    def test_actor_deletion_keeps_row_and_snapshot(self):
        actor = make_user()
        row = log_action(actor, AuditAction.SETTINGS_CHANGE)
        actor_pk = actor.pk
        actor.delete()
        row.refresh_from_db()
        self.assertIsNone(row.actor)
        self.assertEqual(row.actor_id_snapshot, actor_pk)


class TestImmutable(TestCase):

    def setUp(self):
        self.row = log_action(None, AuditAction.SETTINGS_CHANGE, reason='x')

    def test_save_existing_raises(self):
        self.row.reason = 'змінено'
        with self.assertRaisesMessage(ImmutableAuditLog, 'не змінюється'):
            self.row.save()

    def test_delete_raises(self):
        with self.assertRaisesMessage(ImmutableAuditLog, 'не видаляється'):
            self.row.delete()

    def test_queryset_update_and_delete_raise(self):
        with self.assertRaisesMessage(ImmutableAuditLog, 'не змінюється'):
            AuditLog.objects.all().update(reason='x')
        with self.assertRaisesMessage(ImmutableAuditLog, 'не видаляється'):
            AuditLog.objects.all().delete()
        self.assertEqual(AuditLog.objects.count(), 1)


class TestPurge(TestCase):

    def _old_and_new(self):
        old = log_action(None, AuditAction.SETTINGS_CHANGE, reason='old')
        AuditLog._base_manager.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        new = log_action(None, AuditAction.SETTINGS_CHANGE, reason='new')
        return old, new

    @override_settings(AUDIT_LOG_RETENTION_DAYS=0)
    def test_zero_keeps_everything(self):
        self._old_and_new()
        self.assertEqual(purge_audit_log(), 0)
        self.assertEqual(AuditLog.objects.count(), 2)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=30)
    def test_positive_removes_only_old_and_logs_purge(self):
        old, new = self._old_and_new()
        self.assertEqual(purge_audit_log(), 1)
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=new.pk).exists())
        purge = AuditLog.objects.get(action=AuditAction.AUDIT_PURGE)
        self.assertEqual(purge.after, {'deleted': 1, 'retention_days': 30})


class TestNoPiiInBlockEntry(TestCase):

    def test_block_entry_has_no_email(self):
        from users.services import block_user
        admin = make_admin_role('boss-pii@test.com')
        victim = make_user('victim-pii@test.com', phone='+380501112233')
        block_user(victim, admin, 'Спам у коментарях')
        row = AuditLog.objects.get(action=AuditAction.USER_BLOCK)
        dump = f'{row.target_repr} {row.reason} {row.before} {row.after} {row.actor_role_snapshot}'
        for pii in ('victim-pii', 'boss-pii', '@test.com', '380501112233'):
            self.assertNotIn(pii, dump)


class TestAuditAdminAccess(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.row = log_action(None, AuditAction.SETTINGS_CHANGE)

    def test_admin_role_sees_journal(self):
        self.client.force_login(make_admin_role())
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 200)

    def test_superuser_sees_journal(self):
        self.client.force_login(make_staff(superuser=True))
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 200)

    def test_moderator_forbidden(self):
        self.client.force_login(make_moderator())
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 403)
        self.assertEqual(self.client.get(f'{AUDIT_URL}{self.row.pk}/change/').status_code, 403)

    def test_plain_staff_forbidden(self):
        self.client.force_login(make_staff())
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 403)

    def test_role_admin_without_staff_cannot_enter_admin(self):
        self.client.force_login(make_user(role='admin'))
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 302)

    def test_no_add_change_delete_even_for_superuser(self):
        self.client.force_login(make_staff(superuser=True))
        self.assertEqual(self.client.get(f'{AUDIT_URL}add/').status_code, 403)
        self.assertEqual(self.client.get(f'{AUDIT_URL}{self.row.pk}/delete/').status_code, 403)
        resp = self.client.post(f'{AUDIT_URL}{self.row.pk}/change/', {'reason': 'підробка'})
        self.assertEqual(resp.status_code, 403)
        self.row.refresh_from_db()
        self.assertEqual(self.row.reason, '')

    def test_no_public_api(self):
        client = auth_client(make_admin_role())
        self.assertEqual(client.get('/api/v1/audit/').status_code, 404)
