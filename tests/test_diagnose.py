import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DiagnoseTest(unittest.TestCase):
    def run_report(self, failed, green, *flags):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / n for n in ('failed.json', 'green.json')]
            for path, value in zip(paths, (failed, green)):
                path.write_text(json.dumps(value), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(ROOT / 'diagnose.py'), *(str(p) for p in paths), *flags],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.stderr, '')
            return result.returncode, json.loads(result.stdout)

    def test_comparison_excludes_shared_warnings_and_bounds_log(self):
        failed = {'run_id': '18', 'status': 'FAILURE', 'stages': [
            {'name': 'Test', 'status': 'FAILURE', 'duration_ms': 20,
             'log': 'WARN memory\nERROR new\r\nextra\n'},
            {'name': 'Deploy', 'status': 'NOT_RUN'},
        ]}
        green = {'run_id': '17', 'status': 'SUCCESS', 'stages': [
            {'name': 'Test', 'status': 'SUCCESS', 'duration_ms': 11,
             'log': 'WARN memory\nTests passed'},
        ]}
        status, report = self.run_report(failed, green, '--tail-lines', '2')
        self.assertEqual(status, 0)
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['failed_stages']), 1)
        stage = report['failed_stages'][0]
        self.assertEqual(stage['baseline_status'], 'SUCCESS')
        self.assertEqual(stage['duration_delta_ms'], 9)
        self.assertEqual(stage['tail'], ['ERROR new', 'extra'])
        self.assertEqual(stage['novel_signals'], ['ERROR new'])

    def test_absent_baseline_and_terminal_controls(self):
        failed = {'run_id': '18', 'status': 'FAILURE', 'stages': [
            {'name': 'Test', 'status': 'FAILURE', 'log': '\x1b[31mERROR demo\x1b[0m'},
        ]}
        status, report = self.run_report(failed, {'run_id': '17', 'status': 'SUCCESS', 'stages': []})
        self.assertEqual(status, 0)
        self.assertIsNone(report['failed_stages'][0]['baseline_status'])
        self.assertEqual(report['failed_stages'][0]['tail'], ['ERROR demo'])
        self.assertIsNone(report['failed_stages'][0]['duration_delta_ms'])

    def test_wrong_baseline_is_an_input_error(self):
        failed = {'run_id': '18', 'status': 'FAILURE', 'stages': []}
        status, report = self.run_report(failed, {'run_id': '17', 'status': 'FAILURE', 'stages': []})
        self.assertEqual(status, 2)
        self.assertEqual(report['error']['code'], 'invalid_input')

    def test_duplicate_stages_refused(self):
        stage = {'name': 'Sample', 'status': 'FAILURE'}
        status, report = self.run_report(
            {'run_id': '18', 'status': 'FAILURE', 'stages': [stage, stage]},
            {'run_id': '17', 'status': 'SUCCESS', 'stages': []},
        )
        self.assertEqual(status, 2)
        self.assertFalse(report['ok'])
        self.assertIn('duplicate', report['error']['message'])

    def test_char_bound_applies_to_signal_as_well_as_tail(self):
        status, report = self.run_report(
            {'run_id': '18', 'status': 'FAILURE', 'stages': [
                {'name': 'Sample', 'status': 'FAILURE', 'log': 'ERROR ' + 'x' * 500},
            ]},
            {'run_id': '17', 'status': 'SUCCESS', 'stages': []},
            '--line-chars', '20',
        )
        self.assertEqual(status, 0)
        for line in report['failed_stages'][0]['tail'] + report['failed_stages'][0]['novel_signals']:
            self.assertLessEqual(len(line), 20)


if __name__ == '__main__':
    unittest.main()
