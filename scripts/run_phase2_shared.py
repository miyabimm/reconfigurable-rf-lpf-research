#!/usr/bin/env python3
"""Shared diagnostic entrypoint. Never starts an EXP or a real optimizer."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def synthetic(policy_id, inductors):
    from lpf.constraint_versions import load_constraint
    from lpf.phase2_models.api import build_nominal_circuit
    from lpf.phase2_models.circuit_layout import InductorTree
    from lpf.phase2_models.topology_enumeration import TopologySpace, enumerate_topologies
    from lpf.phase2_models.problem_seed import vector_fingerprint
    from lpf.phase2_models.synthetic_plan import make_synthetic_plan
    from lpf.phase2_models.synthetic_runner import run_synthetic

    policy = load_constraint(policy_id, allow_trial=True)
    space = TopologySpace(
        trees=(InductorTree(inductors + 1, tuple((0, i) for i in range(1, inductors + 1))),),
        inductor_assignments=(("LQP02HV",) * inductors,),
        fixed_layouts=(( ((0, 1), "GJM01"), ((1, -1), "PCB_PATTERN_C") ),),
        variable_layouts=(( ((3, -1), "shunt_to_ground"), ((0, 2), "bridge") ),),
        coupling_slot_counts=(inductors - 1,), physical_order_limit=1, max_candidates=1)
    rows = enumerate_topologies(policy, space)['candidates']
    if len(rows) != 1:
        raise ValueError('Synthetic fixture topology unavailable')
    row = rows[0]
    circuit = build_nominal_circuit(policy, row['definition'])
    vector = list(map(float, row['representative_vector']))
    starts = [{'id': 'start-0', 'vector': vector, 'vector_sha256': vector_fingerprint(vector),
               'seed': 0, 'jitter_fraction': 0.0}]
    source = {'kind': 'synthetic', 'policy_id': policy_id, 'vectors': {'start-0': vector}}
    envelope = make_synthetic_plan(circuit, starts, run_id='synthetic-shared',
                                   coarse_points=1, fine_points=2, input_source=source)

    def mock(problem, vector, budget, target):
        return vector, {'converged': True, 'status': 0, 'message': 'synthetic mock',
                        'nit': 0, 'nfev': 0}

    with tempfile.TemporaryDirectory(prefix='lpf-synthetic-') as tmp:
        result = run_synthetic(circuit, envelope, Path(tmp) / 'checkpoint.json', optimize_stage=mock)
    plan = envelope['plan']
    return {'mode': 'synthetic_mock', 'plan_fingerprint': envelope['fingerprint'],
            'policy_id': plan['policy_id'], 'policy_sha256': plan['policy_sha256'],
            'source': plan['source'], 'input_source': plan['input_source'],
            'input_source_sha256': plan['input_source_sha256'], 'grids': plan['grids'],
            'budget': plan['budget'], 'result': result,
            'validation_scope': 'diagnostic mock only; independent RF validation not run',
            'candidate_promotion_blocked': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    diag = sub.add_parser('synthetic', help='bounded explicit mock diagnostic only')
    diag.add_argument('--mock', action='store_true', required=True)
    diag.add_argument('--policy', required=True, choices=('RF-T005', 'RF-T007', 'RF-T008'))
    diag.add_argument('--inductors', required=True, type=int, choices=(3, 4))
    args = parser.parse_args(argv)
    print(json.dumps(synthetic(args.policy, args.inductors), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
