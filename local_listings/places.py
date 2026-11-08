"""Нормализация названий населённых пунктов для поиска и сопоставления (задача 8.2, A3.1/A3.2).

Пользователь печатает «Кам'янське», в реестре «Кам’янське» — это одно имя. Нормализация: нижний регистр,
единый апостроф, единый дефис, схлопнутые пробелы. Результат хранится в ``City.search_name``.
"""
import re

_APOSTROPHES = re.compile(r"[\u2019\u02bc\u2018`\u00b4\u02b9\u2032']")
_DASHES = re.compile(r'[\u2010\u2011\u2012\u2013\u2014\u2015\u2212-]')
_SPACES = re.compile(r'\s+')


def normalize_place_name(value: str) -> str:
    value = (value or '').lower()
    value = _APOSTROPHES.sub("'", value)
    value = _DASHES.sub('-', value)
    value = re.sub(r'\s*-\s*', '-', value)
    return _SPACES.sub(' ', value).strip()
