"""Проверка трассировки (промт 01, шаг 14, пункт 4).

1. Каждая критичная/важная находка отчётов 01–13 есть в основной таблице 24_TRACEABILITY.md.
2. У каждой строки основной таблицы колонка «Задача» ссылается на существующие задачи.
3. Каждый пункт эталона с приоритетом «Запуск» из 31–39_PARITY_*.md есть в разделе
   «Пункты эталона уровня «Запуск»» и привязан к существующей задаче (или помечен «—есть»).
Существующие задачи: файлы docs/tasks/*.md + строки этапа 9 в ROADMAP.md.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
AUDIT = ROOT / 'docs' / 'audit'

tasks = {re.match(r'(\d+\.\d+)', p.name).group(1) for p in (ROOT / 'docs' / 'tasks').glob('*.md')}
roadmap = (ROOT / 'ROADMAP.md').read_text(encoding='utf-8')
tasks |= set(re.findall(r'^\|[^|]*\|\s*(9\.\d+)\s*\|', roadmap, re.M))
TASK_RE = re.compile(r'\b(\d+\.\d+)[ab]?\b')


def cells(line):
    return [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]


def check_refs(cell):
    refs = TASK_RE.findall(cell)
    return refs, [r for r in refs if r not in tasks]


# --- 1. находки отчётов 01–13
expected = set()
for rep in sorted(AUDIT.glob('[01][0-9]_*.md')):
    if not re.match(r'(0[1-9]|1[0-3])_', rep.name):
        continue
    for line in rep.read_text(encoding='utf-8').splitlines():
        m = re.match(r'^\|\s*(\d\d-[SQC]\d+)\s*\|\s*(критично|важно)\b', line)
        if m:
            expected.add(m.group(1))
expected |= {'01-C1', '03-C1', '09-C1', '09-C2', '09-C3', '12-C1', '12-C2'}

trace = (AUDIT / '24_TRACEABILITY.md').read_text(encoding='utf-8')
main_part, _, parity_part = trace.partition('## Пункты эталона уровня «Запуск»')
main_rows = {}
for line in main_part.split('## Итоговые счётчики')[0].splitlines():
    c = cells(line)
    if len(c) >= 8 and re.fullmatch(r'\d\d-[A-Z]\d+', c[0]) and c[1] in ('критично', 'важно'):
        main_rows[c[0]] = c[7]

errors = []
missing = sorted(expected - main_rows.keys())
for fid in missing:
    errors.append(f'находка {fid} отсутствует в основной таблице')
for fid, cell in main_rows.items():
    refs, bad = check_refs(cell)
    if not refs:
        errors.append(f'{fid}: колонка «Задача» без номера задачи: {cell!r}')
    for b in bad:
        errors.append(f'{fid}: задачи {b} не существует')

# --- 3. пункты эталона «Запуск»
launch = {}
for rep in sorted(AUDIT.glob('3[1-9]_PARITY_*.md')):
    for line in rep.read_text(encoding='utf-8').splitlines():
        c = cells(line)
        if len(c) >= 5:
            m = re.match(r'\**([A-R]\d+(?:\.\d+)?)\b', c[0])
            if m and re.match(r'\**Запуск', c[3]):
                launch[m.group(1)] = rep.name
if not parity_part:
    errors.append('нет раздела «Пункты эталона уровня «Запуск»»')
par_rows = {}
for line in parity_part.splitlines():
    c = cells(line)
    if len(c) >= 4 and re.fullmatch(r'[A-R]\d+(?:\.\d+)?', c[0]):
        par_rows[c[0]] = c[3]
extra = sorted(par_rows.keys() - launch.keys())
for code in sorted(launch.keys() - par_rows.keys()):
    errors.append(f'пункт эталона {code} ({launch[code]}) не привязан')
for code, cell in par_rows.items():
    if cell.startswith('—есть'):
        continue
    refs, bad = check_refs(cell)
    if not refs:
        errors.append(f'{code}: колонка «Задача» без номера: {cell!r}')
    for b in bad:
        errors.append(f'{code}: задачи {b} не существует')

print(f'Задач (файлы 0–8 + этап 9 в ROADMAP): {len(tasks)}')
print(f'Критичных/важных находок в отчётах 01–13: {len(expected)}; строк в основной таблице: {len(main_rows)}')
print(f'Пунктов эталона «Запуск» в 31–39: {len(launch)}; строк в разделе трассировки: {len(par_rows)}')
if extra:
    print('В трассировке сверх распознанных в отчётах (проверить вручную):', ', '.join(extra))
print(f'Ошибок: {len(errors)}')
for e in errors:
    print('  -', e)
sys.exit(1 if errors else 0)
