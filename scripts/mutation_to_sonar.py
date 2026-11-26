"""Выжившие мутанты cosmic-ray -> внешние issues SonarQube (generic issue format).

У SonarQube нет плагина мутаций для Python, поэтому каждый выживший мутант становится
issue на мутированной строке: правило `external_cosmic-ray:survived-mutant`.

    python scripts/mutation_to_sonar.py .mutation/*.sqlite -o .mutation/sonar-issues.json

Сканеру: -Dsonar.externalIssuesReportPaths=.mutation/sonar-issues.json (см. scripts/sonar.sh).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

RULE = {
    'id': 'survived-mutant',
    'name': 'Мутант выжил',
    'description': 'Код изменили (мутация cosmic-ray), а все тесты прошли: поведение этой строки '
                   'тестами не проверяется. Допишите тест или, если мутант эквивалентен, '
                   'перепишите строку без эквивалентной формы.',
    'engineId': 'cosmic-ray',
    'cleanCodeAttribute': 'TESTED',
    'impacts': [{'softwareQuality': 'MAINTAINABILITY', 'severity': 'MEDIUM'}],
}
EFFORT_MINUTES = 10

SURVIVORS_SQL = (
    'SELECT s.module_path, s.start_pos_row, s.operator_name, w.diff '
    'FROM mutation_specs s JOIN work_results w ON w.job_id = s.job_id '
    "WHERE w.test_outcome = 'SURVIVED' ORDER BY 1, 2"
)


def _changed_line(diff: str) -> str:
    """Строка после мутации из unified diff (первая добавленная)."""
    for line in (diff or '').splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            return line[1:].strip()
    return ''


def survivors(db: Path) -> list[dict]:
    con = sqlite3.connect(db)
    try:
        rows = con.execute(SURVIVORS_SQL).fetchall()
    finally:
        con.close()
    issues = []
    for path, line, operator, diff in rows:
        operator = operator.split('/', 1)[-1]
        changed = _changed_line(diff)
        message = f'Мутант выжил ({operator}): тесты проходят и после замены на «{changed}»'
        issues.append({
            'ruleId': RULE['id'],
            'effortMinutes': EFFORT_MINUTES,
            'primaryLocation': {
                'message': message[:1000],
                'filePath': str(path).replace('\\', '/'),
                'textRange': {'startLine': int(line)},
            },
        })
    return issues


def build_report(dbs: list[Path]) -> dict:
    issues = [issue for db in dbs for issue in survivors(db)]
    return {'rules': [RULE], 'issues': issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='cosmic-ray -> SonarQube external issues')
    parser.add_argument('sessions', nargs='+', type=Path, help='.mutation/<name>.sqlite')
    parser.add_argument('-o', '--output', type=Path, default=Path('.mutation/sonar-issues.json'))
    args = parser.parse_args(argv)
    missing = [str(p) for p in args.sessions if not p.is_file()]
    if missing:
        print(f'Нет файлов сессий: {", ".join(missing)}', file=sys.stderr)
        return 2
    report = build_report(args.sessions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(report["issues"])} выживших мутантов -> {args.output}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
