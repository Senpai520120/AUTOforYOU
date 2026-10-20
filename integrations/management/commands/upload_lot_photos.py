"""
Management command: upload_lot_photos

Переносит фото лотов из внешних URL (VehicleImage.source_url) в основное хранилище
(S3 или локально), заполняя поле VehicleImage.image.

Запускать ТОЛЬКО при наличии настроенного хранилища.
При USE_S3=False фото сохраняются в media/ локально (только для тестов).

Использование:
  python manage.py upload_lot_photos              # все фото без image
  python manage.py upload_lot_photos --limit 50   # первые 50
  python manage.py upload_lot_photos --dry-run     # показать что будет, не скачивать

Безопасность (задача 1.10, 03-S5): качаем только с хостов из LOT_PHOTO_ALLOWED_HOSTS
(и редиректы — тоже только туда, не больше 3), потоково с обрывом после лимита байт
UPLOAD_IMAGE_MAX_SIZE_MB; тип — по содержимому, EXIF снимается, имя — uuid (core/uploads.py).
Только https; хост (и после редиректа) не должен резолвиться в private/loopback/link-local/
reserved/multicast; общий дедлайн TOTAL_DEADLINE_SECONDS на фото.
Пустой LOT_PHOTO_ALLOWED_HOSTS — команда ничего не качает.

⚠ S3-перенос фото — промт 7. Для продакшена задать S3_BUCKET_NAME, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY (и S3_REGION) в .env.
"""

import io
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.uploads import ImageUploadError, default_max_bytes, sanitize_image
from vehicles.models import VehicleImage

MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 15.0
# Общий дедлайн на одно фото (все редиректы + чтение тела): медленная отдача по байту не держит команду.
TOTAL_DEADLINE_SECONDS = 30.0


class LotPhotoRejected(Exception):
    """Фото не скачано по правилам безопасности (хост, размер, редиректы)."""


def _make_client():
    # follow_redirects=False: каждый редирект проверяется по списку хостов вручную.
    return httpx.Client(follow_redirects=False, timeout=TIMEOUT_SECONDS)


def host_allowed(url, allowed_hosts):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname:
        return False
    host = parts.hostname.lower().rstrip('.')
    for entry in allowed_hosts:
        if entry.startswith('*.'):
            if host.endswith(entry[1:]):
                return True
        elif host == entry:
            return True
    return False


def _resolve(host, port):
    """IP-адреса хоста (вынесено отдельно — тесты подменяют DNS)."""
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def ensure_public_host(url):
    """Хост из allowlist не должен резолвиться во внутреннюю сеть (SSRF через DNS)."""
    parts = urlsplit(url)
    try:
        addresses = _resolve(parts.hostname, parts.port or 443)
    except (OSError, UnicodeError):
        raise LotPhotoRejected(f'хост {parts.hostname} не резолвиться') from None
    if not addresses:
        raise LotPhotoRejected(f'хост {parts.hostname} не резолвиться')
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split('%', 1)[0])
        if getattr(ip, 'ipv4_mapped', None):
            ip = ip.ipv4_mapped
        if (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise LotPhotoRejected(f'хост {parts.hostname} веде на внутрішню адресу {ip}')


def download_limited(client, url, allowed_hosts, max_bytes, deadline_seconds=TOTAL_DEADLINE_SECONDS):
    """Скачать url потоково. Только https; хост и каждый редирект — из allowed_hosts и с публичным IP;
    больше max_bytes или дольше deadline_seconds — отказ."""
    deadline = time.monotonic() + deadline_seconds
    for _ in range(MAX_REDIRECTS + 1):
        if time.monotonic() > deadline:
            raise LotPhotoRejected('перевищено час завантаження')
        if not host_allowed(url, allowed_hosts):
            raise LotPhotoRejected(
                f'{urlsplit(url).hostname or "?"}: не https або хост не в LOT_PHOTO_ALLOWED_HOSTS'
            )
        ensure_public_host(url)
        with client.stream('GET', url) as resp:
            if resp.is_redirect:
                location = resp.headers.get('location')
                if not location:
                    raise LotPhotoRejected('редирект без Location')
                url = urljoin(url, location)
                continue
            resp.raise_for_status()
            declared = resp.headers.get('content-length')
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise LotPhotoRejected('файл більший за ліміт')
            buf = io.BytesIO()
            for chunk in resp.iter_bytes():
                buf.write(chunk)
                if buf.tell() > max_bytes:
                    raise LotPhotoRejected('файл більший за ліміт')
                if time.monotonic() > deadline:
                    raise LotPhotoRejected('перевищено час завантаження')
            return buf.getvalue()
    raise LotPhotoRejected(f'більше {MAX_REDIRECTS} редиректів')


class Command(BaseCommand):
    help = 'Скачивает фото лотов из source_url и сохраняет в хранилище (S3 или local).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Максимум фото за один запуск (0=все)')
        parser.add_argument('--dry-run', action='store_true', help='Показать список без скачивания')

    def handle(self, *args, **options):
        from core.modules import module_enabled
        if not module_enabled('lots'):
            raise CommandError('Каталог лотів заморожено (LOTS_ENABLED=false): імпорт вимкнено (задача 2.8).')
        allowed_hosts = list(getattr(settings, 'LOT_PHOTO_ALLOWED_HOSTS', []) or [])
        if not allowed_hosts:
            self.stdout.write(self.style.WARNING(
                'Перенос фото лотов не настроено: LOT_PHOTO_ALLOWED_HOSTS пустой. Ничего не скачано.'
            ))
            return

        use_s3 = getattr(settings, 'USE_S3', False)
        storage_label = 'S3' if use_s3 else 'локальная папка media/'

        qs = VehicleImage.objects.filter(source_url__gt='', image='').order_by('id')
        limit = options['limit']
        if limit:
            qs = qs[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Нет фото для переноса.'))
            return

        self.stdout.write(f'Найдено {total} фото для переноса → {storage_label}')

        if options['dry_run']:
            for img in qs:
                self.stdout.write(f'  [dry-run] #{img.pk}: {img.source_url}')
            return

        max_bytes = default_max_bytes()
        ok = 0
        fail = 0
        with _make_client() as client:
            for img in qs:
                try:
                    data = download_limited(client, img.source_url, allowed_hosts, max_bytes)
                    content = sanitize_image(io.BytesIO(data), max_bytes=max_bytes)
                    img.image.save(content.name, content, save=True)
                    ok += 1
                    self.stdout.write(f'  ✓ #{img.pk} → {img.image.name}')
                except (LotPhotoRejected, ImageUploadError, httpx.HTTPError, OSError) as exc:
                    fail += 1
                    self.stdout.write(self.style.WARNING(f'  ✗ #{img.pk} {img.source_url}: {exc}'))

        style = self.style.SUCCESS if fail == 0 else self.style.WARNING
        self.stdout.write(style(f'Готово: {ok} успешно, {fail} ошибок.'))
