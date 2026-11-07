"""Настройки хранилищ медиа и статики (задача 7.2, 01-C1, 12-C6).

Чистая функция без Django: settings.py делает `globals().update(build_storage_settings(...))`,
тесты вызывают её с любым набором переменных.

- Без S3-переменных: оба хранилища локальные (dev и сервер без S3).
- S3_BUCKET_NAME + AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY: медиа в S3/R2 (`STORAGES['default']`),
  статика остаётся локальной (её раздаёт nginx из volume).
- MEDIA_URL: CDN-домен (S3_CUSTOM_DOMAIN / AWS_S3_CUSTOM_DOMAIN) → для R2/MinIO (S3_ENDPOINT_URL)
  ссылку даёт storage.url() (подписанные URL) → шаблон amazonaws только для AWS без endpoint.
"""
import os
from collections.abc import Mapping

LOCAL_MEDIA = 'django.core.files.storage.FileSystemStorage'
LOCAL_STATIC = 'django.contrib.staticfiles.storage.StaticFilesStorage'
S3_MEDIA = 'storages.backends.s3boto3.S3Boto3Storage'


def build_storage_settings(env: Mapping, base_dir) -> dict:
    bucket = env.get('S3_BUCKET_NAME', '')
    key = env.get('AWS_ACCESS_KEY_ID', '')
    secret = env.get('AWS_SECRET_ACCESS_KEY', '')
    use_s3 = bool(bucket and key and secret)

    result = {
        'USE_S3': use_s3,
        # MEDIA_ROOT задан всегда: локальные файлы (e2e, sanitize_existing_images) и при S3.
        'MEDIA_ROOT': os.path.join(base_dir, 'media'),
        'STATIC_URL': '/static/',
        'STATIC_ROOT': os.path.join(base_dir, 'staticfiles'),
        'STORAGES': {
            'default': {'BACKEND': S3_MEDIA if use_s3 else LOCAL_MEDIA},
            'staticfiles': {'BACKEND': LOCAL_STATIC},
        },
    }
    if not use_s3:
        result['MEDIA_URL'] = '/media/'
        return result

    region = env.get('S3_REGION', '') or 'eu-central-1'
    endpoint = env.get('S3_ENDPOINT_URL', '')
    custom_domain = (env.get('S3_CUSTOM_DOMAIN', '') or env.get('AWS_S3_CUSTOM_DOMAIN', '')).strip().strip('/')
    result.update({
        'AWS_ACCESS_KEY_ID': key,
        'AWS_SECRET_ACCESS_KEY': secret,
        'AWS_STORAGE_BUCKET_NAME': bucket,
        'AWS_S3_REGION_NAME': region,
        'AWS_S3_FILE_OVERWRITE': False,
        'AWS_DEFAULT_ACL': 'private',
        'AWS_QUERYSTRING_AUTH': True,          # подписанные URL (приватный bucket)
        'AWS_S3_SIGNATURE_VERSION': 's3v4',
    })
    if endpoint:
        result['AWS_S3_ENDPOINT_URL'] = endpoint  # Cloudflare R2 / MinIO
    if custom_domain:
        # Публичный домен bucket'а (CDN, R2 custom domain): ссылки без подписи.
        result['AWS_S3_CUSTOM_DOMAIN'] = custom_domain
        result['AWS_QUERYSTRING_AUTH'] = False
        result['MEDIA_URL'] = f'https://{custom_domain}/'
    elif endpoint:
        # R2/MinIO без публичного домена: URL строит storage.url() (подписанный), не шаблон amazonaws.
        result['MEDIA_URL'] = '/media/'
    else:
        result['MEDIA_URL'] = f'https://{bucket}.s3.{region}.amazonaws.com/'
    return result
