#!/usr/bin/env python3
"""Unwired directory-CI execution prototype; mixed directories remain FULL.

No dependency installation is performed here. The caller must provide the
existing project environment for non-DOC checks. This is not the GitHub workflow.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ci import directory_preview as preview


def run(args, *, env=None):
    print('Running:', ' '.join(args), flush=True)
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def execute(plan, *, manual=False):
    """Execute a locally computed preview; incomplete diff scopes never pass."""
    print('Directory preview:', json.dumps(plan, ensure_ascii=False), flush=True)
    classes = set(plan['classes'])
    full = plan['full']
    comparison = plan['comparison']
    if 'DOC' in classes or full:
        run([sys.executable, '-S', 'ci/verify_phase2_cleanup_w1_links.py', '--project-documents'])
    if full or 'CODE' in classes:
        # Conservative common suite until the legacy selector is retired. Its
        # FULL test runner does not invoke the historical EXP audit_all.
        env = dict(os.environ, CI_EVENT='workflow_dispatch', CI_FULL='true')
        run([sys.executable, 'ci/select_ci_tests.py'], env=env)
        for test in ('test_issue369_forward_window.py', 'test_issue372_diagnostic_io.py'):
            run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', test, '-v'])
    elif 'INPUT' in classes:
        # Reuse the existing RF and RF/Worker boundary regressions without
        # inheriting the old path classification. Transitional, not final CI.
        code = ("import sys; sys.path.insert(0, 'ci'); import select_ci_tests as s; "
                "s.execute({'classes':['RF'], 'full':False, 'reasons':[], "
                "'changed_tests':[], 'storage_only':False})")
        run([sys.executable, '-c', code])
    if comparison and plan['changed_tests']:
        run([sys.executable, 'ci/run_changed_tests.py', '--head', comparison['head'],
             *plan['changed_tests']])
    ids = plan['changed_experiments']
    if ids:
        # Lazy import keeps DOC-only execution independent of installed packages.
        from ci.check_changed_ledger import check, check_index_manifests
        targets = check(ROOT, ids, require_committed=True)
        print('Changed ledger targets:', json.dumps(targets), flush=True)
        indexed_ids = [row['experiment_id'] for row in targets if row['index_present']]
        if indexed_ids:
            check_index_manifests(ROOT, indexed_ids)
        file_ids = {match.group(1) for change in plan['changes'] for path in change['paths']
                    if (match := preview.EXPERIMENT.fullmatch(path))}
        audit_ids = sorted(file_ids | set(indexed_ids))
        if audit_ids:
            if not comparison:
                raise ValueError('cannot audit changed EXP without complete comparison')
            args = [sys.executable, 'scripts/audit_new_experiment_storage.py', 'audit',
                    '--diff-base', comparison['base'], '--expected-head', comparison['head']]
            for ident in audit_ids:
                args.extend(('--selected-exp', ident))
            run(args)
    if plan['removed_ledger_experiments']:
        raise ValueError('removed ledger rows require separate review: ' +
                         ', '.join(plan['removed_ledger_experiments']))
    if not manual and (not comparison or not plan['changed_tests_complete'] or
                       not plan['experiment_scope_complete']):
        raise ValueError('FULL executed where possible, but changed test/EXP scope is incomplete')
    print('G5 remote readback and cleanup are execution-time gates, not certified here.', flush=True)


def main():
    event = os.environ.get('CI_EVENT')
    execute(preview.preview_environment(os.environ), manual=event == 'workflow_dispatch')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('FAIL directory checks: ' + str(exc))
