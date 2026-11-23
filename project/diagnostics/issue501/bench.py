#!/usr/bin/env python3
"""Alternating same-process kernel A/B, baseline git revision vs working tree.

Only the named class methods are swapped; evaluator construction, warmup and
tracemalloc are outside plain timings. No solver or scientific EXP is run.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import scipy
import lpf.rf_core.model as rfmodel
import lpf.rf_core.coupled_lc as coupled
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record


def methods(text, cls, names, globals_):
    tree = ast.parse(text)
    body = next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    result = {}
    for name in names:
        node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
        ns = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<benchmark>', 'exec'), globals_, ns)
        result[name] = ns[name]
    return result


def main(base, output):
    spec = [(coupled, coupled.CoupledLCTopology, 'src/lpf/rf_core/coupled_lc.py', ['matrices', '_matrices_lk', 'node_admittance_with_jacobian']),
            (rfmodel, rfmodel.RFEvaluator, 'src/lpf/rf_core/model.py', ['evaluate_with_il_jacobian'])]
    versions = {}
    hashes = {}
    for label in ('base', 'candidate'):
        versions[label] = []
        hashes[label] = {}
        for module, cls, path, names in spec:
            text = (subprocess.check_output(['git', 'show', f'{base}:{path}'], cwd=ROOT, text=True)
                    if label == 'base' else (ROOT / path).read_text())
            hashes[label][path] = hashlib.sha256(text.encode()).hexdigest()
            versions[label].append((cls, methods(text, cls.__name__, names, vars(module))))
    def select(label):
        for cls, funcs in versions[label]:
            for name, func in funcs.items():
                setattr(cls, name, func)
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
    config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=True, partial_fd=True)
    config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
    plan, _, profile, model, _ = freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]}, search_bounds=None, checkpoint_interval=1000)
    grid = grid_from_record(plan.data['grids']['baseline/search'])
    evaluator = model.evaluator(grid)
    bounds = np.asarray(plan.data['search_bounds']); width = bounds[:,1]-bounds[:,0]
    x = np.asarray(starts['1013']['baseline']['vector'])
    vectors = [x, x + width*np.linspace(-.001, .001, len(x))]
    rows = []
    memory = {}
    for vi, vector in enumerate(vectors):
        for label in ('base', 'candidate'):
            select(label); evaluator.evaluate_with_il_jacobian(vector)
        for order in (('base','candidate'), ('candidate','base'))*10:
            for label in order:
                select(label)
                wall, cpu = time.perf_counter(), time.process_time()
                evaluator.evaluate_with_il_jacobian(vector)
                rows.append(dict(vector=vi, version=label, wall_s=time.perf_counter()-wall,
                                 cpu_s=time.process_time()-cpu, loadavg=os.getloadavg()))
        for label in ('base','candidate'):
            select(label); tracemalloc.start(); evaluator.evaluate_with_il_jacobian(vector)
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            memory[f'{vi}/{label}'] = peak
    metadata = dict(base=base, head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True), source_sha256=hashes,
        plan_sha256=plan.sha256, profile_sha256=profile.fingerprint, rf_profile=plan.data['rf_profile'],
        grids=plan.data['grids'], start=starts['1013']['baseline'], seed=1013,
        vectors=[v.tolist() for v in vectors], python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
        platform=platform.platform(), threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
        note='20 alternating plain repetitions per vector/version; warmup and separate tracemalloc excluded')
    Path(output).write_text(json.dumps(dict(metadata=metadata, rows=rows, python_peak_bytes=memory), indent=2)+'\n')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
