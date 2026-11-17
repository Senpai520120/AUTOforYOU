"""Мониторинг ошибок через протокол Sentry (задача 7.6, 12-S13).

Адаптер: пустой SENTRY_DSN - мониторинг выключен, sentry_sdk даже не импортируется; невалидный DSN
пишет предупреждение и не роняет процесс. Подходит sentry.io и self-hosted GlitchTip (одна переменная).

ПДн не уходят: send_default_pii=False, before_send/before_breadcrumb прогоняют текст через
core.logging_filters.scrub (7.2), выбрасывают cookies, тело запроса, заголовки авторизации и query,
у пользователя остаётся только id.
"""
import logging
import os
import re

from core.logging_filters import scrub

logger = logging.getLogger(__name__)

_enabled = False
_SENSITIVE_HEADERS = {
    'authorization', 'cookie', 'x-csrftoken', 'set-cookie', 'proxy-authorization', 'referer',
    'x-forwarded-for', 'x-real-ip', 'x-api-key',
}
# Query после пути в любой строке события (repr запроса, URL в крошках и спанах): ?q=Иван+Петренко и т.п.
_QUERY_RE = re.compile(r'(/[^\s\'"?#<>]*)\?[^\s\'"<>]*')


def is_enabled() -> bool:
    return _enabled


def _strip_query(text: str) -> str:
    return _QUERY_RE.sub(r'\1', text)


def _scrub_value(value):
    if isinstance(value, str):
        return scrub(_strip_query(value))
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


def _clean_request(request: dict) -> dict:
    request.pop('cookies', None)
    request.pop('data', None)
    request.pop('env', None)
    request['query_string'] = ''
    if request.get('url'):
        request['url'] = scrub(request['url'].split('?', 1)[0])
    headers = request.get('headers') or {}
    request['headers'] = {
        k: _scrub_value(v) for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS
    }
    return request


def _clean_frames(stacktrace):
    for frame in (stacktrace or {}).get('frames') or []:
        frame.pop('vars', None)  # локальные переменные кадров: там бывают email и пароли
        if frame.get('context_line'):
            frame['context_line'] = scrub(frame['context_line'])
        for key in ('pre_context', 'post_context'):
            if frame.get(key):
                frame[key] = [scrub(line) for line in frame[key]]


def before_send(event, hint=None):
    if 'request' in event:
        event['request'] = _clean_request(dict(event['request']))
    user = event.get('user') or {}
    event['user'] = {'id': user['id']} if user.get('id') is not None else {}
    for exc in (event.get('exception') or {}).get('values') or []:
        if exc.get('value'):
            exc['value'] = scrub(exc['value'])
        _clean_frames(exc.get('stacktrace'))
    for thread in (event.get('threads') or {}).get('values') or []:
        _clean_frames(thread.get('stacktrace'))
    if event.get('message'):
        event['message'] = scrub(event['message'])
    logentry = event.get('logentry')
    if logentry:
        if logentry.get('message'):
            logentry['message'] = scrub(logentry['message'])
        if logentry.get('formatted'):
            logentry['formatted'] = scrub(logentry['formatted'])
        logentry['params'] = _scrub_value(logentry.get('params') or [])
    if isinstance(event.get('extra'), dict):
        event['extra'].pop('request', None)  # LoggingIntegration кладёт repr WSGIRequest с query
    for key in ('extra', 'tags', 'contexts'):
        if event.get(key):
            event[key] = _scrub_value(event[key])
    if event.get('transaction'):
        event['transaction'] = _strip_query(event['transaction'])
    for span in event.get('spans') or []:
        if span.get('description'):
            span['description'] = scrub(_strip_query(span['description']))
        if span.get('data'):
            span['data'] = _scrub_value(span['data'])
    if event.get('breadcrumbs'):
        values = event['breadcrumbs'].get('values') if isinstance(event['breadcrumbs'], dict) else event['breadcrumbs']
        for crumb in values or []:
            before_breadcrumb(crumb)
    return event


def before_breadcrumb(crumb, hint=None):
    if crumb.get('message'):
        crumb['message'] = scrub(_strip_query(crumb['message']))
    if crumb.get('data'):
        data = crumb['data']
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != 'request'}
        data = _scrub_value(data)
        if isinstance(data, dict):
            if isinstance(data.get('url'), str):
                data['url'] = data['url'].split('?', 1)[0]
            data.pop('http.query', None)
        crumb['data'] = data
    return crumb


def _is_testing() -> bool:
    try:
        from django.conf import settings
        return bool(settings.configured and getattr(settings, 'IS_TESTING', False))
    except Exception:
        return False


def _truthy(value) -> bool:
    return str(value or '').lower() in ('true', '1', 'yes')


def init_monitoring(component: str, env=None) -> bool:
    """Включает мониторинг в процессе (web / celery / bot). Повторный вызов - no-op."""
    global _enabled
    if env is None:
        if _is_testing():
            return False  # тесты не поднимают настоящий SDK, даже если SENTRY_DSN есть в .env
        env = os.environ
    if _enabled:
        return True
    dsn = env.get('SENTRY_DSN', '').strip()
    if not dsn:
        logger.info('мониторинг ошибок выключен (SENTRY_DSN не задан)')
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        debug = _truthy(env.get('DEBUG'))
        sentry_sdk.init(
            dsn=dsn,
            environment=env.get('SENTRY_ENVIRONMENT', '') or ('development' if debug else 'production'),
            release=env.get('SENTRY_RELEASE', '') or env.get('IMAGE_TAG', '') or None,
            traces_sample_rate=float(env.get('SENTRY_TRACES_SAMPLE_RATE', '') or 0),
            send_default_pii=False,
            max_request_body_size='never',
            include_local_variables=False,
            before_send=before_send,
            # Транзакции (при SENTRY_TRACES_SAMPLE_RATE>0) мимо before_send не проходят - тот же фильтр.
            before_send_transaction=before_send,
            before_breadcrumb=before_breadcrumb,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                # ERROR и logger.exception - события, WARNING и выше - только хлебные крошки.
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
        )
        sentry_sdk.set_tag('component', component)
    except Exception as exc:  # BadDsn и прочее: сайт работает без мониторинга
        logger.warning('мониторинг ошибок не включён: %s', type(exc).__name__)
        return False
    _enabled = True
    logger.info('мониторинг ошибок включён (component=%s)', component)
    return True


def capture_message(message: str, level: str = 'error', extra: dict | None = None) -> bool:
    """Отправить событие. При выключенном мониторинге - no-op, возвращает False."""
    if not _enabled:
        return False
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        for key, value in (extra or {}).items():
            if key == 'component':
                scope.set_tag('component', value)
            scope.set_extra(key, _scrub_value(value))
        sentry_sdk.capture_message(scrub(message), level=level)
    return True
