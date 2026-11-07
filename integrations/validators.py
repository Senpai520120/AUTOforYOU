"""Валидаторы входов внешних API (задача 3.2a). Пока только VIN; номер реестра - при разморозке."""
import re

# ISO 3779: 17 символов, буквы I, O, Q запрещены.
VIN_RE = re.compile(r'[A-HJ-NPR-Z0-9]{17}')

VIN_ERROR_MESSAGE = 'VIN має містити 17 символів: цифри та латинські літери, крім I, O, Q.'


def normalize_vin(raw) -> str:
    return str(raw or '').strip().upper()


def is_valid_vin(vin: str) -> bool:
    """fullmatch: `$` пропустил бы завершающий перевод строки."""
    return bool(VIN_RE.fullmatch(vin))
