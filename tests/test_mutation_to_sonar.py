"""scripts/mutation_to_sonar.py: выжившие мутанты cosmic-ray -> generic issues SonarQube."""
import importlib.util
import json
import sqlite3
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

_spec = importlib.util.spec_from_file_location(
    'mutation_to_sonar', Path(settings.BASE_DIR) / 'scripts' / 'mutation_to_sonar.py')
m2s = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m2s)

DIFF = "--- a\n+++ b\n@@ -61 +61 @@\n-    elif f.fee_type == 'x':\n+    elif f.fee_type <= 'x':\n"


def _session(path: Path, rows):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE mutation_specs (module_path, operator_name, start_pos_row, job_id)')
    con.execute('CREATE TABLE work_results (job_id, test_outcome, diff)')
    for job, (module, op, row, outcome, diff) in enumerate(rows):
        con.execute('INSERT INTO mutation_specs VALUES (?, ?, ?, ?)', (module, op, row, job))
        con.execute('INSERT INTO work_results VALUES (?, ?, ?)', (job, outcome, diff))
    con.commit()
    con.close()


class MutationToSonarTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_only_survivors_become_issues_with_line_and_change(self):
        db = self.dir / 'calc.sqlite'
        _session(db, [
            ('pricing\\calculator.py', 'core/ReplaceComparisonOperator_Eq_LtE', 61, 'SURVIVED', DIFF),
            ('pricing\\calculator.py', 'core/AddNot', 70, 'KILLED', DIFF),
            ('pricing\\calculator.py', 'core/AddNot', 80, None, None),
        ])
        report = m2s.build_report([db])
        self.assertEqual(report['rules'][0]['id'], 'survived-mutant')
        self.assertEqual(len(report['issues']), 1)
        loc = report['issues'][0]['primaryLocation']
        self.assertEqual(loc['filePath'], 'pricing/calculator.py')
        self.assertEqual(loc['textRange'], {'startLine': 61})
        self.assertIn("ReplaceComparisonOperator_Eq_LtE", loc['message'])
        self.assertIn("elif f.fee_type <= 'x':", loc['message'])

    def test_main_writes_json_and_rejects_missing_session(self):
        db, out = self.dir / 's.sqlite', self.dir / 'out' / 'issues.json'
        _session(db, [('core/security_settings.py', 'core/AddNot', 5, 'SURVIVED', '')])
        self.assertEqual(m2s.main([str(db), '-o', str(out)]), 0)
        self.assertEqual(len(json.loads(out.read_text(encoding='utf-8'))['issues']), 1)
        self.assertEqual(m2s.main([str(self.dir / 'nope.sqlite'), '-o', str(out)]), 2)
