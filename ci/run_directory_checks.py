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


def original_evidence_review(plan):
    """Do not silently approve overwrites/deletions of already saved evidence."""
    comparison = plan['comparison']
    if not comparison:
        return []  # The incomplete-comparison gate handles this separately.
    base = comparison['base']
    reasons, stages = [], {}
    for change in plan['changes']:
        kind = change['status'][0]
        path = change['paths'][0]
        match = preview.EXPERIMENT.fullmatch(path)
        if not match or kind == 'A':
            continue
        if kind != 'M':
            reasons.append(path + ' (' + change['status'] + ')')
            continue
        prefix, _, relative = path.partition('/' + match.group(1) + '/')
        if relative not in {'manifest.json', 'storage_record.json'}:
            reasons.append(path + ' (existing evidence modified)')
            continue
        directory = prefix + '/' + match.group(1)
        if directory not in stages:
            try:
                raw = subprocess.check_output(
                    ['git', '-C', str(ROOT), 'show', f'{base}:{directory}/storage_record.json'],
                    stderr=subprocess.PIPE, timeout=30)
                record = json.loads(raw)
                stages[directory] = record.get('stage') if isinstance(record, dict) else None
            except (OSError, subprocess.SubprocessError, ValueError):
                stages[directory] = None
        if stages[directory] not in {'planned', 'running', 'preservation_incomplete'}:
            reasons.append(path + ' (base preservation stage complete or unavailable)')
    return reasons


def execute(plan, *, manual=False):
    """Execute a locally computed preview; incomplete diff scopes never pass."""
    print('Directory preview:', json.dumps(plan, ensure_ascii=False), flush=True)
    classes = set(plan['classes'])
    full = plan['full']
    comparison = plan['comparison']
    if 'DOC' in classes or full:
        run([sys.executable, '-S', 'ci/verify_phase2_cleanup_w1_links.py', '--project-documents'])
    if (full or 'INPUT' in classes) and (comparison or manual):
        head = comparison['head'] if comparison else subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, timeout=30).strip()
        run([sys.executable, 'ci/check_rf_schema2.py', '--head', head])
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
    if comparison and (full or 'EXP' in classes or ids):
        # Keep the existing Git scratch/cache guard even if no EXP ID was
        # identified (e.g. a force-added results/ path in an unknown FULL).
        # This scans the event diff, not unchanged historical EXPs.
        from lpf.experiment_storage_audit import inspect_new_git_files
        inspected = inspect_new_git_files(ROOT, 'origin/main', diff_base=comparison['base'],
                                          expected_head=comparison['head'])
        print('Newly added paths inspected for transient files:', inspected, flush=True)
    if ids:
        # Lazy import keeps DOC-only execution independent of installed packages.
        from ci.check_changed_ledger import check, check_index_manifests
        targets = check(ROOT, ids, require_committed=True)
        print('Changed ledger targets:', json.dumps(targets), flush=True)
        indexed_ids = [row['experiment_id'] for row in targets if row['index_present']]
        missing_candidate_ids = set(plan.get('candidate_experiments', [])) - set(indexed_ids)
        if missing_candidate_ids:
            raise ValueError('candidate target missing from experiment index: ' +
                             ', '.join(sorted(missing_candidate_ids)))
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
    if plan.get('changed_existing_candidates'):
        raise ValueError('existing candidate rows require separate review: ' +
                         ', '.join(plan['changed_existing_candidates']))
    review = original_evidence_review(plan)
    if review:
        raise ValueError('original evidence requires separate review: ' + ', '.join(review))
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
