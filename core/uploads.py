"""Безопасная загрузка изображений (задача 1.10).

Один слой для всех точек, где в проект попадают картинки: API фото C2C, админка,
`Shipment.advance_status(photo=...)`, `upload_lot_photos`, `e2e_seed`.

- `sanitize_image()` — тип по содержимому (Pillow, а не `content_type` клиента и не
  расширение), лимит байт и пикселей, `exif_transpose`, пересохранение без
  EXIF/XMP/GPS/ICC, имя `uuid4().hex` + расширение реального формата.
- `SanitizedImageField` — `ImageField`, у которого каждый новый файл проходит
  `sanitize_image()` при сохранении (`FieldFile.save`, его зовёт и `pre_save`,
  и прямой `instance.image.save(...)`). Уже сохранённые значения не трогаются.
- `validate_image_upload` — валидатор поля: админка показывает ошибку поля, а не 500.
- `private_media_storage` / `private_file_response` — приватное хранилище
  (фото трекинга) и отдача через `X-Accel-Redirect`/`FileResponse`/подписанный URL.

`core` — не приложение (см. ARCHITECTURE.md), это обычный модуль.
"""
import io
import os
import posixpath
import re
import warnings
from urllib.parse import quote
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db.models.fields.files import ImageField, ImageFieldFile
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.utils.deconstruct import deconstructible
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

# Форматы, которые сервис умеет пересохранить. Настройка может только сузить список.
SUPPORTED_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
# Должен совпадать с internal-location в nginx/nginx.conf.
X_ACCEL_PREFIX = '/protected-media/'
SANITIZED_NAME_RE = re.compile(r'^[0-9a-f]{32}\.(jpg|png|webp)$')


def _max_pixels():
    return int(getattr(settings, 'UPLOAD_IMAGE_MAX_PIXELS', 25_000_000))


# Глобальный предохранитель Pillow (decompression bomb) — один раз при импорте, не на каждый вызов:
# > MAX — предупреждение (у нас — отказ), > 2×MAX — ошибка уже в Image.open.
Image.MAX_IMAGE_PIXELS = _max_pixels()


class ImageUploadError(ValueError):
    """Файл не прошёл проверку. Текст — для пользователя, без внутренних путей."""


def _mb_to_bytes(mb):
    return int(mb) * 1024 * 1024


def default_max_bytes():
    return _mb_to_bytes(getattr(settings, 'UPLOAD_IMAGE_MAX_SIZE_MB', 8))


def max_bytes_from_setting(setting_name=None):
    """Лимит из именованной настройки (например LOCAL_LISTING_PHOTO_MAX_SIZE_MB), иначе общий."""
    if setting_name:
        value = getattr(settings, setting_name, None)
        if value:
            return _mb_to_bytes(value)
    return default_max_bytes()


def allowed_formats():
    raw = getattr(settings, 'UPLOAD_IMAGE_ALLOWED_FORMATS', None) or list(SUPPORTED_FORMATS)
    return [f for f in (s.strip().upper() for s in raw) if f in SUPPORTED_FORMATS]


def _allowed_human(formats):
    return '/'.join(SUPPORTED_FORMATS[f] for f in formats)


def _read_limited(file, max_bytes):
    size = getattr(file, 'size', None)
    if max_bytes is not None and isinstance(size, int) and size > max_bytes:
        raise ImageUploadError(_too_big(max_bytes))
    if hasattr(file, 'seek'):
        try:
            file.seek(0)
        except (OSError, ValueError):
            pass
    data = file.read() if max_bytes is None else file.read(max_bytes + 1)
    if max_bytes is not None and len(data) > max_bytes:
        raise ImageUploadError(_too_big(max_bytes))
    if not data:
        raise ImageUploadError('Файл порожній.')
    return data


def _too_big(max_bytes):
    return f'Файл завеликий: максимум {max_bytes // (1024 * 1024)} МБ.'


def _target_mode(img, fmt):
    has_alpha = img.mode in ('RGBA', 'LA', 'PA') or 'transparency' in img.info
    if fmt == 'JPEG':
        return 'L' if img.mode == 'L' else 'RGB'
    if has_alpha:
        return 'RGBA'
    if fmt == 'PNG' and img.mode == 'L':
        return 'L'
    return 'RGB'


def sanitize_image(file, *, max_bytes=None, subdir='', enforce_size=True):
    """Проверить и пересохранить картинку. Возвращает ContentFile с безопасным именем.

    max_bytes=None — общий лимит UPLOAD_IMAGE_MAX_SIZE_MB; enforce_size=False — без лимита
    байт (только для уже лежащих файлов в sanitize_existing_images). Лимит пикселей действует всегда.
    """
    if enforce_size and max_bytes is None:
        max_bytes = default_max_bytes()
    data = _read_limited(file, max_bytes if enforce_size else None)

    formats = allowed_formats()
    max_pixels = _max_pixels()
    bad_type = f'Файл не є зображенням допустимого формату ({_allowed_human(formats)}).'

    with warnings.catch_warnings():
        # DecompressionBombWarning (> MAX_IMAGE_PIXELS) — тоже отказ, а не предупреждение.
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data), formats=formats) as probe:
                probe.verify()
            img = Image.open(io.BytesIO(data), formats=formats)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ImageUploadError(_too_many_pixels(max_pixels)) from None
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, TypeError, EOFError):
            raise ImageUploadError(bad_type) from None

        fmt = img.format
        if fmt not in formats:
            raise ImageUploadError(bad_type)
        width, height = img.size
        if width < 1 or height < 1:
            raise ImageUploadError(bad_type)
        if width * height > max_pixels:
            raise ImageUploadError(_too_many_pixels(max_pixels))
        if getattr(img, 'is_animated', False) or getattr(img, 'n_frames', 1) > 1:
            raise ImageUploadError('Анімовані зображення не підтримуються.')
        try:
            img.load()  # обрезанный файл падает здесь, verify() его не ловит
            img = ImageOps.exif_transpose(img)
            mode = _target_mode(img, fmt)
            if img.mode != mode:
                img = img.convert(mode)
            # exif_transpose/convert вернули новый объект Image (не *ImageFile: нет applist, text,
            # хвоста файла). Метаданные живут только в info — очищаем; save() ниже вызывается
            # без exif=/icc_profile=/pnginfo=/xmp=, а Pillow берёт их из info (PNG icc, JPEG/WEBP xmp).
            clean = img if not isinstance(img, ImageFile.ImageFile) else img.copy()
            clean.info = {}
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ImageUploadError(_too_many_pixels(max_pixels)) from None
        except (OSError, SyntaxError, ValueError, TypeError, EOFError):
            raise ImageUploadError('Файл пошкоджений або обрізаний.') from None

    out = io.BytesIO()
    save_kwargs = {}
    if fmt == 'JPEG':
        save_kwargs = {'quality': int(getattr(settings, 'UPLOAD_IMAGE_JPEG_QUALITY', 85)), 'optimize': True}
    elif fmt == 'WEBP':
        save_kwargs = {'quality': int(getattr(settings, 'UPLOAD_IMAGE_JPEG_QUALITY', 85))}
    clean.save(out, format=fmt, **save_kwargs)

    name = f'{uuid4().hex}.{SUPPORTED_FORMATS[fmt]}'
    if subdir:
        name = posixpath.join(subdir.strip('/'), name)
    content = ContentFile(out.getvalue(), name=name)
    content.afy_sanitized = True
    return content


def _too_many_pixels(max_pixels):
    return f'Зображення завелике за роздільністю: максимум {max_pixels:,} пікселів.'.replace(',', ' ')


# ─── Поле модели ──────────────────────────────────────────────────────────────

@deconstructible
class UuidUploadTo:
    """upload_to: подпапка + uuid-имя. Расширение — только из разрешённых (имя уже очищено)."""

    def __init__(self, subdir):
        self.subdir = subdir.strip('/')

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower().lstrip('.')
        if ext not in SUPPORTED_FORMATS.values():
            ext = 'jpg'
        return f'{self.subdir}/{uuid4().hex}.{ext}'

    def __eq__(self, other):
        return isinstance(other, UuidUploadTo) and other.subdir == self.subdir


class SanitizedImageFieldFile(ImageFieldFile):
    def save(self, name, content, save=True):
        # Сюда приходят и FileField.pre_save (админка, objects.create, advance_status),
        # и прямой instance.image.save(...) (upload_lot_photos, e2e_seed).
        if not getattr(content, 'afy_sanitized', False):
            content = sanitize_image(content, max_bytes=max_bytes_from_setting(self.field.max_size_setting))
        super().save(content.name, content, save=save)

    save.alters_data = True


class SanitizedImageField(ImageField):
    """ImageField, который пропускает каждый новый файл через sanitize_image()."""

    attr_class = SanitizedImageFieldFile

    def __init__(self, *args, max_size_setting=None, **kwargs):
        # Имя настройки с лимитом в МБ (например LOCAL_LISTING_PHOTO_MAX_SIZE_MB); пусто — общий.
        self.max_size_setting = max_size_setting
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.max_size_setting:
            kwargs['max_size_setting'] = self.max_size_setting
        return name, path, args, kwargs

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        if value and not getattr(value, '_committed', True):
            validate_image_upload(value.file, max_size_setting=self.max_size_setting)


def validate_image_upload(file, max_size_setting=None):
    """Валидатор формы/поля на том же сервисе. Ничего не сохраняет."""
    if not file or getattr(file, 'afy_sanitized', False):
        return
    try:
        sanitize_image(file, max_bytes=max_bytes_from_setting(max_size_setting))
    except ImageUploadError as exc:
        raise ValidationError(str(exc), code='unsafe_image') from None
    finally:
        if hasattr(file, 'seek'):
            try:
                file.seek(0)
            except (OSError, ValueError):
                pass


# ─── Приватное хранилище ──────────────────────────────────────────────────────

class PrivateMediaStorage(FileSystemStorage):
    """Файлы вне MEDIA_ROOT; путь читается из PRIVATE_MEDIA_ROOT при каждом обращении
    (override_settings в тестах работает). url() — internal-путь nginx, снаружи он 404."""

    def __init__(self):
        super().__init__(base_url=X_ACCEL_PREFIX)

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def deconstruct(self):
        return ('core.uploads.PrivateMediaStorage', (), {})


def private_media_storage():
    """Callable для storage= (миграции не зависят от окружения)."""
    if getattr(settings, 'USE_S3', False):
        from storages.backends.s3boto3 import S3Boto3Storage

        # Тот же приватный bucket, отдельный префикс, только подписанные URL.
        # custom_domain=None: публичный CDN-домен (S3_CUSTOM_DOMAIN) не должен давать неподписанные ссылки.
        extra = {}
        if getattr(settings, 'PRIVATE_S3_BUCKET_NAME', ''):
            extra['bucket_name'] = settings.PRIVATE_S3_BUCKET_NAME  # отдельный bucket без публичного домена
        return S3Boto3Storage(**extra, location='private', default_acl='private', querystring_auth=True, custom_domain=None,
                              querystring_expire=int(getattr(settings, 'PRIVATE_MEDIA_URL_EXPIRE', 300)),
                              file_overwrite=False)
    return PrivateMediaStorage()


def private_file_response(fieldfile):
    """Ответ с приватным файлом. Права проверяет вызывающий view."""
    storage = fieldfile.storage
    name = fieldfile.name
    if not isinstance(storage, FileSystemStorage):
        return HttpResponseRedirect(storage.url(name))  # подписанный URL S3 с коротким сроком
    if not storage.exists(name):
        raise Http404
    ext = os.path.splitext(name)[1].lower().lstrip('.')
    content_type = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(ext)
    if content_type is None:
        # Файлы до sanitize_existing_images: не отдаём как inline-контент неизвестного типа.
        content_type = 'application/octet-stream'
    if getattr(settings, 'PRIVATE_MEDIA_USE_X_ACCEL', False):
        response = HttpResponse(content_type=content_type)
        response['X-Accel-Redirect'] = X_ACCEL_PREFIX + quote(name)
    else:
        response = FileResponse(storage.open(name, 'rb'), content_type=content_type)
    disposition = 'inline' if content_type.startswith('image/') else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{posixpath.basename(name)}"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
