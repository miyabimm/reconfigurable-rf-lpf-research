"""Explicit read-only Issue #248 comparison: at most 102 forwards / 5712 samples.

Run from repository root:
  uv run --frozen python project/diagnostics/issue248_generic_starts.py /tmp/issue248.json
Reads three immutable manifest blobs, never writes historical evidence or runs solvers.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.limited_candidate_evidence import _identity
from lpf.phase2_models.multistart import generate_starts
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.start_selection import StartSelectionError

SOURCE_MAIN = '6f4a5dacc6e986767120aeebea945732c894948c'


def compare():
    results = []
    for number in (87, 89, 94):
        path = f'experiments/chatgpt_topology_search/runs/EXP-{number:03}/manifest.json'
        try:
            raw = subprocess.check_output(['git', 'show', f'{SOURCE_MAIN}:{path}'], cwd=ROOT)
        except subprocess.CalledProcessError:
            results.append({'source': path, 'status': 'not_run', 'reason': 'Saved definition unavailable'})
            continue
        scope = json.loads(raw)['search_scope']
        source, origin = scope['input_source'], scope['input_source_origin']
        assert origin['generated_start']['generation_method'] == 'nominal_design'
        d = source['definition']
        tree = dict(d['inductor_tree'], edges=tuple(map(tuple, d['inductor_tree']['edges'])))
        caps = {k: tuple(map(tuple, v)) if k.endswith('edges') else v
                for k, v in d['capacitor_placement'].items()}
        definition = CircuitDefinition(InductorTree(**tree), tuple(d['inductor_types']),
            tuple(d['physical_order']), tuple(map(tuple, d['coupling_pairs'])),
            CapacitorPlacement(**caps), tuple(d['fixed_c_types']), tuple(d['variable_roles']))
        circuit = build_nominal_circuit(load_constraint('RF-T008', allow_trial=True), definition)
        identity = _identity(circuit, source['vector'])
        for pool in ('sobol', 'physical_transform'):
            row = {'class': origin['class_name'], 'source': path,
                   'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                   'identity': identity, 'definition': asdict(definition),
                   'seed': 23, 'candidate_pool': pool}
            try:
                generated = generate_starts(SampledEpigraph(circuit, 2), source['vector'],
                    seed=23, selection='rf_pareto', candidate_pool=pool, max_initial_samples=952)
                row.update(status='complete', selected_vector_sha256=[
                    s['vector_sha256'] for s in generated['starts']],
                    selection_report=generated['selection_report'])
            except StartSelectionError as exc:
                row.update(status='failed', selection_report=exc.report)
            results.append(row)
    costs = [r['selection_report']['cost'] for r in results if 'selection_report' in r]
    assert sum(c['RF_forward_calls'] for c in costs) <= 102
    assert sum(c['frequency_samples_requested'] for c in costs) <= 5712
    return {'issue': 248, 'source_main': SOURCE_MAIN, 'mode': 'read_only_forward_no_solver',
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'candidate_promotion_blocked': True, 'rf_compliance_certified': False,
            'results': results}


if __name__ == '__main__':
    Path(sys.argv[1]).write_text(json.dumps(compare(), separators=(',', ':'), allow_nan=False) + '\n')
