import logging

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.views.decorators.http import require_POST

from . import registry
from .base import MODE_DEMO, mask_secrets
from .models import IntegrationHealth, OutboxMessage, RegistryReport, VinReport

logger = logging.getLogger(__name__)


@admin.register(VinReport)
class VinReportAdmin(admin.ModelAdmin):
    list_display = ('vin', 'provider', 'demo', 'created_at')
    list_filter = ('provider', 'demo')
    search_fields = ('vin',)
    readonly_fields = ('vin', 'provider', 'report_data', 'demo', 'created_at')


@admin.register(RegistryReport)
class RegistryReportAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'provider', 'vin', 'plate', 'demo', 'created_at')
    list_filter = ('provider', 'demo')
    search_fields = ('vin', 'plate')
    readonly_fields = ('vin', 'plate', 'provider', 'payload', 'demo', 'created_at')


# ─── Статус интеграций (задача 3.1) ──────────────────────────────────────────

STATUS_PERM = 'integrations.view_integrationhealth'


@admin.register(IntegrationHealth)
class IntegrationHealthAdmin(admin.ModelAdmin):
    """Журнал здоровья провайдеров: только чтение."""
    list_display = ('provider_key', 'last_success_at', 'last_error_at', 'error_count', 'skipped_count')
    readonly_fields = ('provider_key', 'last_success_at', 'last_error_at', 'last_error', 'error_count',
                       'skipped_count')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboxMessage)
class OutboxMessageAdmin(admin.ModelAdmin):
    """Демо-отправки (письма, Telegram): только чтение."""
    list_display = ('created_at', 'provider', 'recipient', 'subject')
    list_filter = ('provider',)
    readonly_fields = ('provider', 'recipient', 'subject', 'body', 'created_at')

    def has_view_permission(self, request, obj=None):
        # В теле писем бывают ссылки сброса пароля и подтверждения: только суперпользователь.
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def status_view(request):
    """/admin/integrations/status/: таблица провайдеров. Значения ключей не выводятся."""
    if not request.user.has_perm(STATUS_PERM):
        raise PermissionDenied
    context = {
        **admin.site.each_context(request),
        'title': 'Статус інтеграцій',
        'statuses': registry.get_statuses(),
    }
    return TemplateResponse(request, 'admin/integrations/status.html', context)


def _check_status_perm(request):
    """Кнопки запускают внешние вызовы и пишут письма: только суперпользователь (и с правом на страницу)."""
    if not (request.user.is_superuser and request.user.has_perm(STATUS_PERM)):
        raise PermissionDenied


@require_POST
def refresh_nbu_view(request):
    """Кнопка «Оновити курс НБУ»: загрузка курса сейчас. Результат - сообщением админки."""
    _check_status_perm(request)
    from pricing.nbu import refresh_rates
    from pricing.rates_provider import NbuRateProvider

    mode = NbuRateProvider().resolution().mode
    try:
        updated = refresh_rates()
    except Exception as exc:  # noqa: BLE001 - любая причина показывается админу, секреты маскируются
        messages.error(request, f'Не вдалося оновити курс НБУ: {type(exc).__name__}: {mask_secrets(exc)[:200]}')
    else:
        if not updated:
            messages.warning(request, 'Курс не оновлено: NBU_MODE вимикає завантаження.')
        else:
            demo = ' (демо-курс, не НБУ)' if mode == MODE_DEMO else ''
            messages.success(request, f'Курс оновлено{demo}: {", ".join(updated)}')
    return redirect('admin:integrations_status')


@require_POST
def test_email_view(request):
    """Кнопка «Надіслати тестовий лист»: лист на email текущего админа, доставка сразу."""
    _check_status_perm(request)
    from .email import send_email

    to = request.user.email
    if not to:
        messages.error(request, 'У вашого облікового запису не вказано email.')
        return redirect('admin:integrations_status')
    result = send_email(
        to, 'AUTOforYOU: тестовий лист', 'Це тестовий лист зі сторінки «Статус інтеграцій». Відповідати не потрібно.',
        sync=True,
    )
    if not result['configured']:
        messages.warning(request, f'Лист не надіслано: {result["reason"]}')
    elif not result['queued']:
        messages.error(request, f'Не вдалося надіслати лист: {result.get("error", "помилка")}. Деталі - у «Остання помилка».')
    elif result['mode'] == MODE_DEMO:
        messages.success(request, 'Демо: лист записано в Outbox і консоль, назовні не надсилався.')
    else:
        messages.success(request, f'Тестовий лист надіслано на {to}.')
    return redirect('admin:integrations_status')


@require_POST
def check_liqpay_view(request):
    """Кнопка «Перевірити конфігурацію LiqPay»: только настройки, без запросов к API LiqPay."""
    _check_status_perm(request)
    from payments.providers import LiqPayProvider

    provider = LiqPayProvider()
    res = provider.resolution()
    if res.configured:
        kind = 'sandbox (реальні гроші не списуються)' if provider.is_sandbox else 'бойовий режим'
        messages.success(request, f'LiqPay налаштовано: {kind}. Запити до LiqPay не надсилалися.')
    else:
        messages.warning(request, f'LiqPay: {res.reason}')
    return redirect('admin:integrations_status')


@require_POST
def check_bot_view(request):
    """Кнопка «Перевірити бота»: getMe и getWebhookInfo. Токен в сообщение не попадает."""
    _check_status_perm(request)
    from telegram_bot.provider import RealTelegramProvider, TelegramProvider

    res = TelegramProvider().resolution()
    if not res.configured:
        messages.warning(request, f'Telegram: {res.reason}')
    elif res.mode == MODE_DEMO:
        messages.success(request, 'Демо: бот не перевіряється, повідомлення пишуться в Outbox.')
    else:
        try:
            info = RealTelegramProvider().check()
        except Exception as exc:  # noqa: BLE001 - причина показывается админу, токен маскируется
            messages.error(request, f'Не вдалося перевірити бота: {mask_secrets(exc)[:200]}')
        else:
            webhook = info['webhook_url'] or 'не встановлено (polling)'
            messages.success(request, f'Бот: @{info["username"]}. Webhook: {webhook}.')
    return redirect('admin:integrations_status')


_original_get_urls = admin.site.get_urls
_original_index = admin.site.index


def _get_urls():
    custom = [
        path('integrations/status/', admin.site.admin_view(status_view), name='integrations_status'),
        path('integrations/status/refresh-nbu/', admin.site.admin_view(refresh_nbu_view),
             name='integrations_refresh_nbu'),
        path('integrations/status/test-email/', admin.site.admin_view(test_email_view),
             name='integrations_test_email'),
        path('integrations/status/check-liqpay/', admin.site.admin_view(check_liqpay_view),
             name='integrations_check_liqpay'),
        path('integrations/status/check-bot/', admin.site.admin_view(check_bot_view),
             name='integrations_check_bot'),
    ]
    return custom + _original_get_urls()


def _index(request, extra_context=None):
    extra = dict(extra_context or {})
    if request.user.has_perm(STATUS_PERM):
        extra['integrations_status_link'] = True
        extra['integrations_attention'] = registry.attention_needed()
    return _original_index(request, extra)


admin.site.get_urls = _get_urls
admin.site.index = _index
admin.site.index_template = 'admin/integrations/index.html'
