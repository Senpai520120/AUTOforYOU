"""Задача 3.4a: почтовый адаптер - режимы, асинхронная отправка, ошибки без утечек, письма проекта через него."""
import smtplib
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from core.tasks import ResilientTask
from integrations import email as email_service
from integrations.admin import OutboxMessageAdmin
from integrations.checks import check_integration_modes
from integrations.email import EMAIL_UNAVAILABLE_DETAIL, EmailProvider, send_email
from integrations.models import IntegrationHealth, OutboxMessage, write_outbox
from integrations.tasks import send_email_task
from local_listings.models import LocalListing
from local_listings.services import approve_listing
from tests.base import CleanCacheTestCase
from tests.factories import make_local_listing, make_staff, make_user
from users.models import DealerApplication
from users.services import anonymize_user, approve_application

RESET_URL = '/api/v1/auth/password-reset/'
RESEND_URL = '/api/v1/auth/verify-email/resend/'
SMTP = 'django.core.mail.backends.smtp.EmailBackend'
CONSOLE = 'django.core.mail.backends.console.EmailBackend'


class EmailStatusTests(SimpleTestCase):

    @override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.mail.test', DEFAULT_FROM_EMAIL='a@mail.test')
    def test_auto_smtp_is_real(self):
        status = EmailProvider().status()
        self.assertEqual((status.mode, status.configured), ('real', True))

    @override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=CONSOLE, EMAIL_HOST='smtp.mail.test', DEFAULT_FROM_EMAIL='a@mail.test')
    def test_auto_console_backend_not_configured(self):
        status = EmailProvider().status()
        self.assertEqual((status.mode, status.configured), ('off', False))
        self.assertIn('Не налаштовано', status.reason)

    @override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.mail.test', DEFAULT_FROM_EMAIL='')
    def test_auto_without_sender_not_configured(self):
        self.assertFalse(EmailProvider().is_configured())

    @override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.mail.test',
                       DEFAULT_FROM_EMAIL='your_email@example.com')
    def test_auto_placeholder_sender_not_configured(self):
        self.assertFalse(EmailProvider().is_configured())

    @override_settings(EMAIL_MODE='real', EMAIL_BACKEND=CONSOLE, DEFAULT_FROM_EMAIL='a@mail.test')
    def test_real_with_console_backend_is_config_error(self):
        status = EmailProvider().status()
        self.assertEqual((status.mode, status.configured), ('real', False))

    @override_settings(EMAIL_MODE='demo', EMAIL_BACKEND=CONSOLE, DEFAULT_FROM_EMAIL='')
    def test_demo_is_configured_without_smtp(self):
        status = EmailProvider().status()
        self.assertEqual((status.mode, status.configured), ('demo', True))

    @override_settings(EMAIL_MODE='off')
    def test_off(self):
        self.assertEqual(EmailProvider().mode, 'off')

    def test_status_lists_env_names_not_values(self):
        with override_settings(EMAIL_HOST_PASSWORD='super-secret-password'):
            status = EmailProvider().status()
        self.assertIn('EMAIL_HOST_PASSWORD', status.env_vars)
        self.assertNotIn('super-secret-password', repr(status))


class SendEmailTests(CleanCacheTestCase):

    def test_real_sends_from_default_from_email_through_celery(self):
        result = send_email('to@mail.test', 'Тема', 'Текст')
        self.assertEqual((result['configured'], result['queued'], result['mode']), (True, True, 'real'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'noreply@afy-mail.test')
        self.assertEqual(mail.outbox[0].to, ['to@mail.test'])

    def test_task_uses_resilient_base(self):
        self.assertIsInstance(send_email_task, ResilientTask)

    def test_queued_via_celery_delay(self):
        with mock.patch.object(send_email_task, 'delay') as delay:
            send_email('to@mail.test', 'Тема', 'Текст')
        delay.assert_called_once_with('to@mail.test', 'Тема', 'Текст')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_TIMEOUT=7)
    def test_timeout_passed_to_connection(self):
        with mock.patch.object(email_service, 'get_connection', wraps=email_service.get_connection) as conn:
            send_email('to@mail.test', 'Тема', 'Текст')
        conn.assert_called_once_with(timeout=7)

    @override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=CONSOLE)
    def test_not_configured_is_not_queued(self):
        with mock.patch.object(send_email_task, 'delay') as delay:
            result = send_email('to@mail.test', 'Тема', 'Текст')
        self.assertEqual((result['configured'], result['queued']), (False, False))
        delay.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_MODE='off')
    def test_off_sends_nothing(self):
        result = send_email('to@mail.test', 'Тема', 'Текст')
        self.assertFalse(result['configured'])
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_MODE='demo')
    def test_demo_writes_outbox_and_sends_nothing(self):
        with mock.patch('sys.stdout'):
            result = send_email('to@mail.test', 'Тема', 'Текст')
        self.assertEqual(result['mode'], 'demo')
        self.assertEqual(len(mail.outbox), 0)
        row = OutboxMessage.objects.get()
        self.assertEqual((row.provider, row.recipient, row.subject), ('email', 'to@mail.test', 'Тема'))

    def test_queue_failure_does_not_raise(self):
        with mock.patch.object(send_email_task, 'delay', side_effect=RuntimeError('broker down')):
            result = send_email('to@mail.test', 'Тема', 'Текст')
        self.assertEqual((result['configured'], result['queued']), (True, False))

    def test_smtp_error_recorded_without_recipient(self):
        err = smtplib.SMTPRecipientsRefused({'victim@mail.test': (550, b'no such user')})
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=err):
            with self.assertLogs('integrations', level='WARNING') as logs:
                result = send_email('victim@mail.test', 'Тема', 'Текст')
        self.assertFalse(result['queued'])
        row = IntegrationHealth.objects.get(provider_key='email')
        self.assertIsNotNone(row.last_error_at)
        self.assertNotIn('victim@mail.test', row.last_error)
        self.assertNotIn('victim@mail.test', '\n'.join(logs.output))

    def test_success_records_health(self):
        send_email('to@mail.test', 'Тема', 'Текст')
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='email').last_success_at)


class OutboxTests(CleanCacheTestCase):

    @override_settings(DEMO_OUTBOX_KEEP=3)
    def test_keeps_only_last_records(self):
        for i in range(5):
            write_outbox('telegram', recipient=str(i), body=f'msg {i}')
        self.assertEqual(
            list(OutboxMessage.objects.order_by('pk').values_list('body', flat=True)), ['msg 2', 'msg 3', 'msg 4'],
        )

    def test_admin_is_read_only(self):
        admin_obj = OutboxMessageAdmin(OutboxMessage, mock.Mock())
        request = mock.Mock()
        self.assertFalse(admin_obj.has_add_permission(request))
        self.assertFalse(admin_obj.has_change_permission(request))


class ProjectMailsThroughServiceTests(CleanCacheTestCase):

    def _application(self):
        user = make_user('dealer@mail.test')
        return DealerApplication.objects.create(
            user=user, company_name='ТОВ', full_name='Марія', contact_phone='+380671234567',
        )

    def test_dealer_approval_mail_uses_default_from(self):
        with self.captureOnCommitCallbacks(execute=True):
            approve_application(self._application(), make_staff())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'noreply@afy-mail.test')
        self.assertEqual(mail.outbox[0].to, ['dealer@mail.test'])

    def test_listing_moderation_mail_uses_default_from(self):
        listing = make_local_listing(make_user('owner@mail.test'), status=LocalListing.Status.PENDING)
        approve_listing(listing, make_staff())
        self.assertEqual([m.to for m in mail.outbox], [['owner@mail.test']])
        self.assertEqual(mail.outbox[0].from_email, 'noreply@afy-mail.test')

    def test_smtp_failure_does_not_break_dealer_approval(self):
        application = self._application()
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=smtplib.SMTPException('down')):
            with self.captureOnCommitCallbacks(execute=True):
                approve_application(application, make_staff())
        application.refresh_from_db()
        user = application.user
        user.refresh_from_db()
        self.assertTrue(user.is_verified_dealer)
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='email').last_error_at)

    def test_smtp_failure_log_has_no_recipient(self):
        application = self._application()
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=smtplib.SMTPException('refused dealer@mail.test')):
            with self.assertLogs(level='WARNING') as logs, self.captureOnCommitCallbacks(execute=True):
                approve_application(application, make_staff())
        self.assertNotIn('dealer@mail.test', '\n'.join(logs.output))
        self.assertNotIn('dealer@mail.test', IntegrationHealth.objects.get(provider_key='email').last_error)

    def test_dealer_mail_is_sent_only_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            approve_application(self._application(), make_staff())
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 1)

    def test_no_hardcoded_sender_left(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        for rel in ('users/services.py', 'local_listings/services.py', 'users/emails.py'):
            self.assertNotIn('noreply@autoforyou.ua', (root / rel).read_text(encoding='utf-8'))


@override_settings(EMAIL_MODE='auto', EMAIL_BACKEND=CONSOLE)
class NotConfiguredEndpointsTests(CleanCacheTestCase):

    def test_password_reset_says_not_configured(self):
        make_user('someone@mail.test')
        resp = APIClient().post(RESET_URL, {'email': 'someone@mail.test'}, format='json')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {'detail': EMAIL_UNAVAILABLE_DETAIL, 'configured': False})
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_same_answer_for_unknown_email(self):
        resp = APIClient().post(RESET_URL, {'email': 'nobody@mail.test'}, format='json')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['detail'], EMAIL_UNAVAILABLE_DETAIL)

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_captcha_failure_is_answered_before_not_configured(self):
        resp = APIClient().post(RESET_URL, {'email': 'x@mail.test', 'website': 'http://spam'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'captcha_failed')

    def test_resend_verification_says_not_configured(self):
        client = APIClient()
        client.force_authenticate(make_user('new@mail.test', verified=False))
        resp = client.post(RESEND_URL)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['configured'], False)


class ConfiguredEndpointsTests(CleanCacheTestCase):

    @override_settings(SITE_URL='https://site.test')
    def test_password_reset_still_sends_through_service(self):
        make_user('someone@mail.test')
        cache.clear()
        resp = APIClient().post(RESET_URL, {'email': 'someone@mail.test'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, 'noreply@afy-mail.test')


class TestEmailButtonTests(CleanCacheTestCase):
    URL = '/admin/integrations/status/test-email/'

    @override_settings(EMAIL_MODE='demo')
    def test_superuser_demo_writes_outbox_to_own_email(self):
        admin = make_staff('boss@mail.test', superuser=True)
        self.client.force_login(admin)
        with mock.patch('sys.stdout'):
            resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Демо')
        row = OutboxMessage.objects.get()
        self.assertEqual((row.provider, row.recipient), ('email', 'boss@mail.test'))

    def test_real_mode_sends_test_mail(self):
        self.client.force_login(make_staff('boss@mail.test', superuser=True))
        resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Тестовий лист надіслано')
        self.assertEqual(mail.outbox[0].to, ['boss@mail.test'])

    @override_settings(EMAIL_MODE='off')
    def test_not_configured_shows_reason(self):
        self.client.force_login(make_staff('boss@mail.test', superuser=True))
        resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Лист не надіслано')
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_error_shown_without_recipient(self):
        self.client.force_login(make_staff('boss@mail.test', superuser=True))
        with mock.patch('django.core.mail.EmailMessage.send',
                        side_effect=smtplib.SMTPException('rejected victim@leak.test')):
            resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Не вдалося надіслати лист')
        self.assertNotContains(resp, 'victim@leak.test')

    def test_send_email_task_retry_attributes(self):
        self.assertEqual(
            (send_email_task.max_retries, send_email_task.retry_backoff, send_email_task.retry_backoff_max),
            (6, 60, 900),
        )

    def test_password_reset_task_retry_attributes(self):
        from users.tasks import send_password_reset_email_task as task
        self.assertEqual((task.max_retries, task.retry_backoff, task.retry_backoff_max), (6, 60, 900))

    def test_staff_with_view_permission_but_not_superuser_gets_403(self):
        from django.contrib.auth.models import Permission
        staff = make_staff('viewer@mail.test')
        staff.user_permissions.add(Permission.objects.get(codename='view_integrationhealth'))
        self.client.force_login(staff)
        resp = self.client.post(self.URL)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_regular_user_redirected_to_login(self):
        self.client.force_login(make_user())
        resp = self.client.post(self.URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])
        self.assertEqual(len(mail.outbox), 0)

    def test_staff_without_permission_gets_403(self):
        self.client.force_login(make_staff('staff@mail.test'))
        resp = self.client.post(self.URL)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)


class SenderAndDemoLeakTests(CleanCacheTestCase):

    @override_settings(EMAIL_MODE='real', EMAIL_BACKEND=SMTP, EMAIL_HOST='smtp.mail.test')
    def test_service_domain_sender_not_configured(self):
        for sender in ('noreply@localhost', 'noreply@example.org', 'noreply@example.com'):
            with override_settings(DEFAULT_FROM_EMAIL=sender):
                self.assertFalse(EmailProvider().is_configured(), sender)
        with override_settings(DEFAULT_FROM_EMAIL='noreply@real-domain.ua'):
            self.assertTrue(EmailProvider().is_configured())

    @override_settings(EMAIL_MODE='demo', SITE_URL='https://site.test')
    def test_demo_does_not_print_body_or_address(self):
        import io
        from contextlib import redirect_stdout

        from users.emails import send_password_reset_email
        user = make_user('secret.person@mail.test')
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertLogs('integrations.email', level='INFO') as logs:
            send_password_reset_email(user)
        shown = buf.getvalue() + '\n'.join(logs.output)
        for needle in ('token=', 'uid=', 'secret.person@mail.test', 'password-reset/confirm'):
            self.assertNotIn(needle, shown)
        self.assertIn('token=', OutboxMessage.objects.get().body)  # тело - только в Outbox

    @override_settings(EMAIL_MODE='demo', DEBUG=False)
    def test_demo_mail_in_production_is_error(self):
        self.assertIn('integrations.E002', [m.id for m in check_integration_modes()])

    @override_settings(EMAIL_MODE='demo', DEBUG=True)
    def test_demo_mail_in_debug_is_allowed(self):
        self.assertNotIn('integrations.E002', [m.id for m in check_integration_modes()])

    def test_outbox_visible_only_to_superuser(self):
        admin_obj = OutboxMessageAdmin(OutboxMessage, mock.Mock())
        req = mock.Mock()
        req.user = make_staff('s@mail.test')
        self.assertFalse(admin_obj.has_view_permission(req))
        req.user = make_staff('su@mail.test', superuser=True)
        self.assertTrue(admin_obj.has_view_permission(req))

    def test_anonymize_removes_outbox_of_that_address(self):
        user = make_user('victim@mail.test')
        write_outbox('email', recipient='Victim@mail.test', subject='s', body='link')
        write_outbox('email', recipient='other@mail.test', subject='s', body='link')
        anonymize_user(user)
        self.assertEqual(list(OutboxMessage.objects.values_list('recipient', flat=True)), ['other@mail.test'])

    def test_schema_still_contains_calculator(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(request=None, public=True)
        post = schema['paths']['/api/v1/pricing/calculate/']['post']
        self.assertEqual(post['summary'], 'Калькулятор стоимости «под ключ»')  # декоратор не повис на функции


class ResetTaskDirectDeliveryTests(CleanCacheTestCase):

    @override_settings(SITE_URL='https://site.test')
    def test_worker_delivers_directly_without_second_delay(self):
        from users.tasks import send_password_reset_email_task
        make_user('owner@mail.test')
        with mock.patch.object(send_email_task, 'delay') as delay:
            send_password_reset_email_task('owner@mail.test')
        delay.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(SITE_URL='https://site.test')
    def test_smtp_failure_propagates_for_retry(self):
        from integrations.email import EmailDeliveryError
        from users.tasks import send_password_reset_email_task
        make_user('owner@mail.test')
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=smtplib.SMTPException('down')):
            with self.assertRaises(EmailDeliveryError):
                send_password_reset_email_task('owner@mail.test')

    def test_task_uses_resilient_base(self):
        from users.tasks import send_password_reset_email_task
        self.assertIsInstance(send_password_reset_email_task, ResilientTask)
