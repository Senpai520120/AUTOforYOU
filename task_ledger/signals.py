"""Окончательная неудача Celery-задачи -> FailedTask и событие в мониторинг (задача 8.9).

task_failure приходит один раз: после исчерпанных повторов (на промежуточных - task_retry).
Обработчик никогда не бросает исключение: ошибка записи только логируется (без аргументов задачи).
"""
import logging

from celery.signals import task_failure

from core.monitoring import capture_message

logger = logging.getLogger(__name__)


@task_failure.connect
def record_failed_task(sender=None, task_id=None, exception=None, args=None, kwargs=None, **extra):
    task_name, retries, exception_class = 'unknown', 0, ''
    try:
        task_name = str(getattr(sender, 'name', None) or sender)
        request = getattr(sender, 'request', None)
        retries = int(getattr(request, 'retries', 0) or 0)
        delivery = getattr(request, 'delivery_info', None) or {}
        exception_class = type(exception).__name__ if exception is not None else ''
        from .models import FailedTask
        from .sanitize import safe_args, safe_error, safe_kwargs

        FailedTask.objects.create(
            task_name=task_name[:200], task_id=str(task_id or '')[:64], retries=retries,
            exception_class=exception_class[:200], error=safe_error(exception) if exception is not None else '',
            args=safe_args(args), kwargs=safe_kwargs(kwargs),
            queue=str(delivery.get('routing_key') or '')[:100],
        )
    except Exception:
        logger.exception('Не удалось записать FailedTask для %s', task_name)
    try:
        capture_message(
            f'Celery task failed: {task_name}', level='error',
            extra={'task_name': task_name, 'task_id': str(task_id or ''), 'retries': retries,
                   'exception_class': exception_class},
        )
    except Exception:
        logger.exception('Не удалось отправить в мониторинг неудачу %s', task_name)
