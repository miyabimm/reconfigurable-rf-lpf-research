#!/usr/bin/env python3
"""Conservative, Git-based CI selection. FULL is an execution mode, not a class.

Sparse mode uses the same plan but runs only tests that can run without
historical evidence. Unregistered paths and uncertain comparisons select FULL.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import classify_storage_ci as storage

CLASSES = ('DOC', 'RF', 'OPT', 'RUN', 'GATE', 'STORE', 'CI')
# Existing smoke modules, grouped by responsibility. Boundary modules can occur
# in more than one group; the runner deduplicates them.
SUITES = {
    'DOC': '''test_phase2_current_status_review.py''',
    'RF': '''test_circuit.py test_evaluate.py test_rf_f003_t005.py test_trial_pcb_pattern_c_t008.py test_trial_ic_fixed_c_t008.py test_trial_shunt_dtc.py test_phase2_candidate_catalog.py test_exp047_legacy_manifest_adapter.py test_issue309_rf_core.py test_issue311_performance.py test_issue313_preflight.py test_phase2_post_search_validation.py test_phase2_circuit_layout.py test_phase2_rft008_layout.py test_phase2_generic_coupled_lc.py test_phase2_rft008_policy_circuit.py test_phase2_rft005_t007_policy_circuit.py test_phase2_public_circuit_api.py test_phase2_branch_mna.py test_phase2_independent_rf.py test_phase2_connection_roles.py test_phase2_s2p_grid_cache.py test_phase2_numeric_diagnostics.py test_phase2_zero_branch_projection.py test_canonical_source_aliases.py test_audit.py test_rf_f002_t004.py test_research_catalog.py test_shared_variable_c_layouts.py test_coupling_layout.py test_matching_numeric_reference.py test_twoport_reduction.py test_three_variable_c_trials.py''',
    'OPT': '''test_phase2_candidate_records.py test_phase2_problem_seed.py test_phase2_sampled_epigraph.py test_phase2_staged_optimization.py test_phase2_frequency_exchange.py test_phase2_optimizer_comparison.py test_phase2_rf_pipeline_adapter.py test_hybrid_optimizer.py test_phase2_scipy_de_preview.py test_phase2_generic_starts.py test_phase2_normalized_epigraph.py test_phase2_post_search_validation.py test_phase2_real_scipy_smoke.py test_slsqp_budget.py test_topology_selection.py test_search_space_extensions.py test_grounded_enumeration.py test_p4_sharding.py test_issue315_fixed_stage.py test_issue309_rf_core.py''',
    'RUN': '''test_issue315_fixed_stage.py test_issue317_fixed_worker.py test_issue319_parent_runner.py test_issue321_development_cli.py test_issue325_campaign.py test_issue325_campaign_gates.py test_issue323_dependencies.py test_shared_checkpoint_io.py test_phase2_rf_pipeline_adapter.py''',
    'GATE': '''test_issue313_preflight.py test_issue325_campaign_gates.py test_issue323_dependencies.py test_experiment_number_reservation.py test_experiment_provenance.py''',
    'STORE': '''test_experiment_number_reservation.py test_experiment_provenance.py test_new_experiment_storage.py test_issue325_campaign_gates.py''',
    'CI': '''test_github_actions_yaml_keys.py test_storage_ci_classification.py test_ci_test_selection.py''',
}
SUITES = {k: tuple(v.split()) for k, v in SUITES.items()}
EXTRA_FULL = '''test_shared_graph_core.py test_graph_instantiation.py test_shared_graph_builder.py test_phase2_candidate_records_frozen.py'''.split()
SPARSE = {
    'RF': '''test_constraint_versioning test_issue307_history test_issue307_snapshot_equivalence test_issue307_constraints test_issue309_rf_core test_issue311_performance test_issue313_preflight test_phase2_s2p_grid_cache.Phase2S2PCacheAndGridTests.test_28_segments_six_settings_and_frequency_endpoints test_pi_sparse_rf''',
    'OPT': 'test_issue315_fixed_stage',
    'RUN': 'test_issue315_fixed_stage test_issue317_fixed_worker test_issue319_parent_runner test_issue321_development_cli test_issue325_campaign test_issue325_campaign_gates test_issue323_dependencies',
    'GATE': 'test_issue313_preflight test_issue325_campaign_gates test_issue323_dependencies',
    'STORE': 'test_issue325_campaign_gates', 'DOC': '', 'CI': 'test_github_actions_yaml_keys test_storage_ci_classification test_ci_test_selection',
}
SPARSE = {k: tuple(v.split()) for k, v in SPARSE.items()}
RF_RUN_BOUNDARY = (
    'test_issue317_fixed_worker.FixedWorkerTests.test_frozen_independent_samples_in_worker',
    'test_issue325_campaign.CampaignTests.test_real_rf_f003_and_explicit_trial_392_with_one_independent_spot',
)
BOUNDARY = '''test_phase2_shared_entry.SharedEntryTests.test_driver_unsupported_policies_never_preflight_or_dispatch
test_phase2_shared_entry.SharedEntryTests.test_scipy_opt_in_provenance_not_synthetic
test_phase2_shared_entry.FrozenConfigTests.test_yaml_read_only_hash_stability_and_invalid_inputs
test_phase2_shared_entry.FrozenConfigTests.test_g1_complete_seed_input_without_preparation_or_rf
test_phase2_shared_entry.FrozenConfigTests.test_budget_exhaustion_partial_failure_and_interrupt_are_distinct
test_phase2_shared_entry.FrozenConfigTests.test_curated_lossless_vectors_and_fail_closed_references
test_phase2_shared_entry.FrozenConfigTests.test_gate_rejects_sparse_before_dispatch
test_phase2_synthetic_runner.SyntheticRunnerTests.test_resume_and_failure
test_phase2_synthetic_runner.SyntheticRunnerTests.test_interrupted_start_fails_closed
test_phase2_topology_enumeration.TopologyEnumerationTests.test_all_six_nominal_structures_components_area_and_trial_stamps
test_phase2_topology_enumeration.TopologyEnumerationTests.test_exact_identity_counterexamples_no_unsafe_canonical_merges
test_phase2_topology_enumeration.TopologyEnumerationTests.test_illegal_branch_and_component_cases_rejected_not_silently_repaired'''.split()

# Explicit ownership, with unknowns failing closed rather than guessing by suffix.
PATHS = {
    'project/specification.md': 'RF', 'project/slsqp_iteration_policy.md': 'OPT',
    'project/experiment_storage_policy.md': 'STORE', 'project/campaign_workflow.md': 'GATE RUN STORE',
    'project/roadmap.md': 'DOC', 'project/README.md': 'DOC', 'README.md': 'DOC',
    'src/lpf/search/gates.py': 'GATE', 'src/lpf/search/preflight.py': 'GATE',
    'src/lpf/search/checkout.py': 'GATE STORE',
    'src/lpf/experiment_preservation.py': 'STORE FULL',
    'src/lpf/search/worker.py': 'RUN STORE', 'src/lpf/search/runner.py': 'RUN STORE',
    'src/lpf/search/_job_evaluation.py': 'RUN RF', 'src/lpf/search/evaluation.py': 'RUN RF',
    'src/lpf/search/campaign.py': 'RUN GATE STORE', 'src/lpf/search/controller.py': 'RUN GATE',
    'src/lpf/search/storage.py': 'STORE RUN', 'src/lpf/search/preservation.py': 'STORE RUN',
    'src/lpf/search/starts.py': 'OPT', 'src/lpf/search/proposals.py': 'RUN GATE',
    'src/lpf/search/performance.py': 'RF RUN', 'src/lpf/search/problem.py': 'OPT RF',
    'src/lpf/search/component_constraints.py': 'RF OPT', 'src/lpf/search/validation.py': 'RF RUN',
    'src/lpf/search/plan.py': 'GATE RUN',
    'scripts/run_rf_search.py': 'RUN', 'scripts/audit_new_experiment_storage.py': 'STORE',
    'scripts/reserve_experiment_number.py': 'STORE GATE', 'scripts/experiment_id_registry.py': 'STORE GATE',
    'scripts/verify_phase2_cleanup_w1_links.py': 'DOC',
}
# Retained legacy scientific tests still have callers. Retired re-exports and
# kernels now owned by rf_core must not have stale legacy ownership entries.
# Shared/moved kernels and structural files stay unknown => conservative FULL.
for name in '''independent_scan rft008_policy_circuit rft005_t007_policy_circuit _grid'''.split():
    PATHS[f'src/lpf/phase2_models/{name}.py'] = 'RF'
for name in '''candidate_records problem_seed sampled_epigraph staged_optimization frequency_exchange frequency_exchange_c1 optimizer_comparison rf_pipeline_adapter scipy_de_preview generic_starts normalized_epigraph start_selection designed_starts multistart topology_enumeration'''.split():
    PATHS[f'src/lpf/phase2_models/{name}.py'] = 'OPT'
for name in '''experiment_run experiment_config synthetic_runner synthetic_plan'''.split():
    PATHS[f'src/lpf/phase2_models/{name}.py'] = 'RUN GATE STORE'
for name in '''post_search_validation post_search_evidence post_search_journal experiment_post_search limited_candidate_evidence'''.split():
    PATHS[f'src/lpf/phase2_models/{name}.py'] = 'RF STORE'


def path_classes(path):
    if path in PATHS:
        return set(PATHS[path].split())
    if path.startswith('docs/') and path.endswith('.md'):
        return {'DOC'}
    if path in {'rf/bands.csv', 'rf/constraints/registry.json',
                'rf/parasitics/circuit1_ant_coupler_0_6ghz.s2p',
                'rf/parasitics/circuit2_poc_through_0_6ghz.s2p'} or re.fullmatch(
                    r'rf/constraints/(?:formal/RF-F003|trial/RF-T00[5-8])\.json', path):
        return {'RF'}
    if path in {'src/lpf/rf_core/model.py', 'src/lpf/rf_core/independent.py'}:
        return {'RF'}
    if path in {f'src/lpf/optimizers/{name}.py' for name in ('_objectives', 'hybrid', 'pipeline', 'slp', 'slsqp')}:
        return {'OPT'}
    if path.startswith('.github/') or path in {'scripts/select_ci_tests.py', 'scripts/classify_storage_ci.py'}:
        return {'CI', 'FULL'}
    if path.startswith('tests/') and re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', path):
        name = path.split('/')[-1]
        found = {group for group, files in SUITES.items() if name in files}
        found |= {group for group, modules in SPARSE.items() if name[:-3] in modules}
        if name in EXTRA_FULL or name in {'test_phase2_shared_entry.py', 'test_phase2_synthetic_runner.py', 'test_phase2_topology_enumeration.py'}:
            found.add('FULL')
        return found or {'FULL'}
    return {'FULL'}


def changes(event, base, head, ref):
    if event not in {'pull_request', 'push'} or ref != 'main' or any(not re.fullmatch(r'[0-9a-f]{40}', x or '') or x == '0' * 40 for x in (base, head)):
        raise ValueError('invalid event, branch or object ID')
    if storage.git('rev-parse', 'HEAD').strip().decode() != head:
        raise ValueError('HEAD mismatch')
    if event == 'pull_request':
        base = storage.git('merge-base', base, head).strip().decode()
    elif subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode:
        raise ValueError('push is not fast-forward')
    raw = storage.git('-c', 'diff.renames=copies', 'diff', '--no-ext-diff', '--no-textconv', '--find-renames', '--find-copies', '--find-copies-harder', '-l0', '--name-status', '-z', base, head, '--')
    fields = raw.split(b'\0')
    if not raw or len(raw) > storage.MAX_DIFF_BYTES or fields.pop() != b'' or len(fields) % 2 or len(fields) // 2 > storage.MAX_PATHS:
        raise ValueError('empty, oversized or malformed diff')
    paths = []
    for status, name in zip(fields[::2], fields[1::2]):
        if status not in (b'A', b'M'):
            raise ValueError('delete, rename, copy or abnormal status')
        path = name.decode('utf-8')
        for rev in ((base, head) if status == b'M' else (head,)):
            entry = storage.git('ls-tree', '-z', rev, '--', path).rstrip(b'\0').split(b'\t', 1)
            if len(entry) != 2 or entry[1] != name or entry[0].split()[:2] != [b'100644', b'blob']:
                raise ValueError('abnormal file mode')
        paths.append((path, status.decode('ascii')))
    return paths


def recover_changed_tests(event, base, head, ref):
    """Even an unsafe diff must not hide added/modified test modules."""
    if event not in {'pull_request', 'push'} or ref != 'main' or any(
            not re.fullmatch(r'[0-9a-f]{40}', x or '') or x == '0' * 40 for x in (base, head)):
        raise ValueError('cannot establish test diff')
    if storage.git('rev-parse', 'HEAD').strip().decode() != head:
        raise ValueError('HEAD mismatch')
    if event == 'pull_request':
        base = storage.git('merge-base', base, head).strip().decode()
    elif subprocess.run(['git', 'merge-base', '--is-ancestor', base, head],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode:
        raise ValueError('push is not fast-forward')
    raw = storage.git('diff', '--no-ext-diff', '--no-textconv', '--no-renames',
                      '--diff-filter=AM', '--name-only', '-z', base, head, '--', 'tests/')
    if len(raw) > storage.MAX_DIFF_BYTES or (raw and not raw.endswith(b'\0')):
        raise ValueError('test diff unavailable')
    return [name for item in raw.split(b'\0') if item
            if re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', name := item.decode('utf-8'))]


def plan(event, base, head, ref, force=False):
    result = {'classes': [], 'full': False, 'reasons': [], 'changed_tests': [], 'storage_only': False}
    try:
        if force:
            raise ValueError('explicit FULL')
        paths = changes(event, base, head, ref)
        result['changed_tests'] = [p for p, _ in paths if re.fullmatch(r'tests/test_[A-Za-z0-9_]+\.py', p)]
        # Preserve the existing deliberately narrow storage fast path unchanged.
        result['storage_only'] = storage.classify(event, base, head, ref)
        if result['storage_only']:
            result['classes'] = ['STORE']
            return result
        selected = set()
        for path, status in paths:
            groups = path_classes(path)
            selected.update(groups - {'FULL'})
            # New code/data needs explicit registration and review, even inside
            # an otherwise familiar directory. New documentation and tests are
            # safe to identify; changed tests are always executed in normal CI.
            new_unknown = status == 'A' and not (path.startswith('docs/') and path.endswith('.md')) and not path.startswith('tests/')
            if 'FULL' in groups or new_unknown:
                result['full'] = True
                result['reasons'].append('unregistered, new or shared path: ' + path)
        result['classes'] = [x for x in CLASSES if x in selected]
    except Exception as exc:
        result['full'] = True
        result['reasons'].append('comparison unavailable: ' + str(exc))
        if not force:
            try:
                result['changed_tests'] = recover_changed_tests(event, base, head, ref)
            except Exception:
                result['reasons'].append('changed tests cannot be independently verified')
    return result


def execute(plan_data, sparse):
    groups = CLASSES if plan_data['full'] else plan_data['classes']
    modules = set()
    # The existing strict storage-only fast path retains only the unconditional
    # storage checks in normal CI; it must not expand to G3-G5 integration.
    suite_groups = () if plan_data['storage_only'] and not plan_data['full'] else groups
    if sparse:
        for group in suite_groups:
            modules.update(SPARSE[group])
        # Sparse cannot run arbitrary evidence-dependent changed tests. Normal CI
        # executes them explicitly; never silently claim they ran here.
    else:
        for group in suite_groups:
            modules.update(SUITES[group])
        if plan_data['full']:
            modules.update(EXTRA_FULL)
        modules.update(Path(p).name for p in plan_data['changed_tests'])
    print('Selection:', json.dumps(plan_data, ensure_ascii=False), flush=True)
    print('Unselected classes:', ', '.join(x for x in CLASSES if x not in groups) or '(none)', flush=True)
    print('Test units:', ', '.join(sorted(modules)) or '(none)', flush=True)
    boundary = not sparse and (plan_data['full'] or bool(set(groups) & {'RF', 'OPT', 'RUN', 'GATE'}))
    links = not sparse and (plan_data['full'] or 'DOC' in groups)
    rf_run = ('RF' in groups and 'RUN' not in groups and not plan_data['full']
              and not plan_data['storage_only'])
    extra = (BOUNDARY if boundary else []) + (list(RF_RUN_BOUNDARY) if rf_run else []) + (['active-only local links'] if links else [])
    print('Additional test units:', ', '.join(extra) or '(none)', flush=True)
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as out:
            out.write(f"### {'Sparse' if sparse else 'Normal'} CI selection\n\n- FULL: {plan_data['full']}\n- Reasons: {', '.join(plan_data['reasons']) or 'none'}\n- Selected: {', '.join(groups) or 'none'}\n- Unselected: {', '.join(x for x in CLASSES if x not in groups) or 'none'}\n- Planned test units: {', '.join(sorted(modules) + extra) or 'none'}\n\nSee step log for actually executed units and outcome.\n")
    env = dict(os.environ)
    env['PYTHONPATH'] = 'tests' + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    if sparse:
        env['PI_SPARSE_RF'] = '1'
    elif plan_data['full'] or set(groups) & {'RF', 'OPT', 'RUN'}:
        print('Running compileall for current RF and search sources', flush=True)
        subprocess.run([sys.executable, '-m', 'compileall', '-q', 'src/lpf/topology_management',
                        'src/lpf/phase2_models', 'src/lpf/rf_core'], check=True, env=env)
    for module in sorted(modules):
        if sparse:
            command = [sys.executable, '-m', 'unittest', '-v', module]
        else:
            if not Path('tests', module).is_file():
                raise RuntimeError('missing selected test: ' + module)
            command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', module, '-v']
        if module == 'test_phase2_candidate_records_frozen.py':
            env['LPF_EVIDENCE_ROOT'] = os.getcwd()
        print('Running:', ' '.join(command), flush=True)
        subprocess.run(command, check=True, env=env)
    if boundary:
        print('Running boundary units:', ', '.join(BOUNDARY), flush=True)
        subprocess.run([sys.executable, '-m', 'unittest', '-v', *BOUNDARY], check=True, env=env)
    if rf_run:
        print('Running RF/Worker boundary units:', ', '.join(RF_RUN_BOUNDARY), flush=True)
        subprocess.run([sys.executable, '-m', 'unittest', '-v', *RF_RUN_BOUNDARY], check=True, env=env)
    if links:
        print('Running active-only local links', flush=True)
        subprocess.run([sys.executable, 'scripts/verify_phase2_cleanup_w1_links.py', '--active-only'], check=True, env=env)


def main():
    event = os.getenv('CI_EVENT')
    force = os.getenv('CI_FULL') == 'true' or event == 'workflow_dispatch'
    selected = plan(event, os.getenv('CI_BASE'), os.getenv('CI_HEAD'), os.getenv('CI_BASE_REF'), force)
    if event == 'pull_request' and (not os.getenv('CI_HEAD_REF') or os.getenv('CI_HEAD_REF') != os.getenv('CI_EVENT_HEAD_REF')):
        selected['full'] = True
        selected['reasons'].append('PR head branch mismatch or missing')
    if event == 'push' and os.getenv('CI_REF') != 'refs/heads/main':
        selected['full'] = True
        selected['reasons'].append('push branch mismatch or missing')
    execute(selected, '--sparse' in sys.argv)
    if 'changed tests cannot be independently verified' in selected['reasons']:
        raise RuntimeError('FULL ran, but changed tests could not be verified')


if __name__ == '__main__':
    main()
