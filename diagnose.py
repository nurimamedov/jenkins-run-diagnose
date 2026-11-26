"""An offline comparison tool for two deliberately exported run snapshots."""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

SCHEMA_VERSION = 1
MAX_BYTES = 2 * 1024 * 1024
MAX_STAGES = 100
STATUSES = {'SUCCESS', 'FAILURE', 'ABORTED', 'UNSTABLE', 'NOT_RUN'}
SIGNAL = re.compile(r'\b(?:ERROR|FATAL|WARN(?:ING)?|EXCEPTION|TIMEOUT)\b', re.IGNORECASE)
ANSI = re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))')


def clean(text):
    return ''.join(ch for ch in ANSI.sub('', text) if not unicodedata.category(ch).startswith('C'))


def meaningful_lines(log):
    return [line for raw in log.splitlines() if (line := clean(raw).strip())]


def label(value, role, field):
    if not isinstance(value, str) or not value or len(value) > 128 or clean(value) != value:
        raise ValueError(f'{role}: invalid {field}')
    return value


def read_snapshot(path, role, status):
    try:
        with Path(path).open('rb') as handle:
            body = handle.read(MAX_BYTES + 1)
    except OSError:
        raise ValueError(f'{role}: cannot read snapshot') from None
    if len(body) > MAX_BYTES:
        raise ValueError(f'{role}: snapshot exceeds {MAX_BYTES} bytes')
    try:
        run = json.loads(body)
    except (ValueError, RecursionError):
        raise ValueError(f'{role}: malformed JSON snapshot') from None
    if not isinstance(run, dict) or run.get('status') != status:
        raise ValueError(f'{role}: expected a run with status {status}')
    run_id = label(run.get('run_id'), role, 'run_id')
    stages = run.get('stages')
    if not isinstance(stages, list) or len(stages) > MAX_STAGES:
        raise ValueError(f'{role}: expected a list of up to {MAX_STAGES} stages')
    by_name = {}
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError(f'{role}: every stage must be an object')
        name = label(stage.get('name'), role, 'stage name')
        if name in by_name:
            raise ValueError(f'{role}: duplicate stage name')
        state, duration, log = stage.get('status'), stage.get('duration_ms'), stage.get('log', '')
        if not isinstance(state, str) or state not in STATUSES or not isinstance(log, str):
            raise ValueError(f'{role}: invalid stage status or log')
        if duration is not None and (type(duration) is not int or not 0 <= duration <= 2**53 - 1):
            raise ValueError(f'{role}: invalid stage duration_ms')
        by_name[name] = (state, duration, meaningful_lines(log))
    return run_id, by_name


def compare(failed_path, green_path, line_limit, char_limit):
    failed_id, failure = read_snapshot(failed_path, 'failed', 'FAILURE')
    green_id, baseline = read_snapshot(green_path, 'baseline', 'SUCCESS')
    if green_id == failed_id:
        raise ValueError('failed and baseline run IDs must differ')
    result = []
    for name, (state, elapsed, lines) in failure.items():
        if state != 'FAILURE':
            continue
        old_state, old_duration, old_lines = baseline.get(name, (None, None, []))
        seen = set(old_lines)
        signals = []
        for line in lines:
            if SIGNAL.search(line) and line not in seen:
                seen.add(line)
                signals.append(line)
        result.append({
            'name': name,
            'baseline_status': old_state,
            'duration_delta_ms': None if elapsed is None or old_duration is None else elapsed - old_duration,
            'tail': [line[:char_limit] for line in lines[-line_limit:]],
            'novel_signals': [line[:char_limit] for line in signals[-line_limit:]],
        })
    return {
        'schema_version': SCHEMA_VERSION,
        'ok': True,
        'failed_run': failed_id,
        'baseline_run': green_id,
        'failed_stages': result,
    }


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('failed_snapshot')
    parser.add_argument('last_green_snapshot')
    parser.add_argument('--tail-lines', type=int, default=8, metavar='1..40')
    parser.add_argument('--line-chars', type=int, default=160, metavar='16..240')
    try:
        args = parser.parse_args(argv)
        if not 1 <= args.tail_lines <= 40 or not 16 <= args.line_chars <= 240:
            raise ValueError('expected --tail-lines in 1..40 and --line-chars in 16..240')
        report = compare(args.failed_snapshot, args.last_green_snapshot, args.tail_lines, args.line_chars)
        status = 0
    except ValueError as exc:
        report = {'schema_version': SCHEMA_VERSION, 'ok': False,
                  'error': {'code': 'invalid_input', 'message': clean(str(exc))[:240]}}
        status = 2
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return status


if __name__ == '__main__':
    sys.exit(main())
