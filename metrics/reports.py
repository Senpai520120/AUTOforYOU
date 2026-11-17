"""Еженедельный отчёт о воронке для владельца (9.50). Только счётчики, без ПДн.

Визиты и расчёты - из DailyMetric. Заявки - из Lead, как в «Воронке» 2.15 (спам не исключается).
Депозит и выкуп - события журнала за период: заявка могла прийти раньше, поэтому это не когорта.
Пороги сюда не входят: репозиторий публичный.
"""
import logging
import re
from datetime import date, datetime, time, timedelta
from statistics import median

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from leads.funnel import source_counts
from leads.models import Lead, LeadPartnerStatusChange, NotifyStatus, PartnerStatus, Qualification
from task_ledger.models import FailedTask

from .models import DailyMetric, MetricKey

logger = logging.getLogger(__name__)

TOP_SOURCES = 5
SOURCE_MAX_LEN = 40
LONG_DIGITS_RE = re.compile(r'\d{7,}')
HIDDEN_SOURCE = '(приховано)'
EMAIL_SUBJECT = 'AUTOforYOU: воронка за період'


def report_period(days: int, today: date | None = None) -> tuple[date, date]:
    """Последние days полных дней, вчера включительно (даты по TIME_ZONE)."""
    end = (today or timezone.localdate()) - timedelta(days=1)
    return end - timedelta(days=days - 1), end


def _metric_total(key: str, start: date, end: date) -> int:
    rows = DailyMetric.objects.filter(key=key, date__gte=start, date__lte=end)
    return rows.aggregate(total=Sum('value'))['total'] or 0


def collect_funnel(start: date, end: date) -> dict:
    tz = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(start, time.min), tz)
    until = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)

    leads = Lead.objects.filter(created_at__gte=since, created_at__lt=until)
    changes = LeadPartnerStatusChange.objects.filter(created_at__gte=since, created_at__lt=until)

    def status_leads(status: str) -> int:
        return changes.filter(to_status=status).values('lead_id').distinct().count()

    answered = Lead.objects.filter(first_response_at__gte=since, first_response_at__lt=until)
    delays = [
        (answered_at - created_at).total_seconds()
        for answered_at, created_at in answered.values_list('first_response_at', 'created_at')
    ]
    undelivered = leads.exclude(telegram_status=NotifyStatus.SENT).exclude(email_status=NotifyStatus.SENT)

    return {
        'start': start,
        'end': end,
        'landing_visits': _metric_total(MetricKey.LANDING_VISIT, start, end),
        'calculator_visits': _metric_total(MetricKey.CALCULATOR_VISIT, start, end),
        'calculations': _metric_total(MetricKey.CALCULATION, start, end),
        'leads': leads.count(),
        'hot': leads.filter(qualification=Qualification.HOT).count(),
        'no_answer': status_leads(PartnerStatus.NO_ANSWER),
        'deposits': status_leads(PartnerStatus.DEPOSIT),
        'bought': status_leads(PartnerStatus.BOUGHT),
        'median_response_seconds': median(delays) if delays else None,
        'sources': source_counts(leads)[:TOP_SOURCES],
        'failed_tasks': FailedTask.objects.filter(failed_at__gte=since, failed_at__lt=until).count(),
        'undelivered': undelivered.count(),
    }


def _percent(part: int, whole: int) -> str:
    return f'{100 * part / whole:.1f}%' if whole else '—'


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return 'немає даних'
    hours, minutes = divmod(round(seconds / 60), 60)
    return f'{hours} год {minutes} хв'


def _source_label(raw: str) -> str:
    # clean_attribution пропускает цифры: номер телефона из utm_source не должен попасть в отчёт.
    if LONG_DIGITS_RE.search(raw):
        return HIDDEN_SOURCE
    return ' '.join(raw.split())[:SOURCE_MAX_LEN]


def render_report(data: dict) -> str:
    """Простой текст без разметки: utm_source приходит из URL и не должен разбираться как HTML в Telegram."""
    visits = data['landing_visits'] + data['calculator_visits']
    lines = [
        f"Воронка AUTOforYOU, {data['start']:%d.%m.%Y} – {data['end']:%d.%m.%Y}",
        '',
        f"Візити лендингів: {data['landing_visits']}",
        f"Візити калькулятора: {data['calculator_visits']}",
        f"Розрахунки: {data['calculations']}",
        f"Заявки: {data['leads']}",
        f"Гарячі заявки: {data['hot']}",
        f"Депозити: {data['deposits']}",
        f"Викупи: {data['bought']}",
        f"Не додзвонились: {data['no_answer']}",
        '',
        'Конверсії:',
        f"візит → заявка: {_percent(data['leads'], visits)}",
        f"розрахунок → заявка: {_percent(data['leads'], data['calculations'])}",
        f"заявка → гаряча: {_percent(data['hot'], data['leads'])}",
        f"гаряча → депозит: {_percent(data['deposits'], data['hot'])}",
        f"депозит → викуп: {_percent(data['bought'], data['deposits'])}",
        f"не додзвонились: {_percent(data['no_answer'], data['leads'])}",
        '',
        f"Медіана першої відповіді: {_duration(data['median_response_seconds'])}",
        f"Недоставлені заявки: {data['undelivered']}",
        f"Невдалі завдання: {data['failed_tasks']}",
    ]
    if data['sources']:
        lines += ['', 'Джерела заявок:']
        lines += [f'{_source_label(name)}: {count}' for name, count in data['sources']]
    lines += ['', 'Депозити й викупи - події за період, заявка могла надійти раніше.']
    return '\n'.join(lines)


def build_report(days: int = 7, today: date | None = None) -> str:
    start, end = report_period(days, today)
    return render_report(collect_funnel(start, end))


def dispatch_report(text: str) -> list[str]:
    """Ставит отправку в очередь по настроенным каналам и возвращает их имена. Каналы не зависят друг от друга."""
    from integrations.email import send_email

    from .tasks import send_funnel_report_telegram

    channels = []
    if settings.FUNNEL_REPORT_EMAIL:
        result = send_email(settings.FUNNEL_REPORT_EMAIL, EMAIL_SUBJECT, text)
        if result.get('queued'):
            channels.append('email')
        else:
            logger.warning('funnel_report: письмо не поставлено в очередь')
    if settings.FUNNEL_REPORT_CHAT_ID:
        send_funnel_report_telegram.delay(text)
        channels.append('telegram')
    if not channels:
        logger.warning('funnel_report: нет доступного канала')
    return channels
