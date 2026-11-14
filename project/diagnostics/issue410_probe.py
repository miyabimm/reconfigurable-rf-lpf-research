#!/usr/bin/env python3
"""Issue #410 only: opt-in C assembly hypotheses, not a production fast path.

Pass --variant baseline|six|split followed by benchmark_minimal_worker arguments.
No RF response, cascade, validation threshold or optimizer changes.
"""
import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import numpy as np
from lpf.rf_core.coupled_lc import CoupledLCTopology, CircuitValues, ParameterVectorSchema
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management.circuit_layout import incidence_matrix


@dataclass(frozen=True)
class ProbeTopology(CoupledLCTopology):
    schema: ParameterVectorSchema
    variant: str

    def node_admittance(self, values, omega_rad_s, setting_indices):
        # Same input/STOP boundary as the baseline; only C assembly differs.
        if not isinstance(values, CircuitValues):
            raise TypeError('Expected CircuitValues')
        omega = np.asarray(omega_rad_s, dtype=float)
        raw_setting = np.asarray(setting_indices)
        if raw_setting.dtype.kind not in 'iu':
            raise ValueError('Setting indices must be integers')
        setting = raw_setting.astype(int)
        if (omega.ndim != 1 or setting.shape != omega.shape or
                not np.all(np.isfinite(omega)) or np.any(omega <= 0) or
                np.any(setting < 0) or np.any(setting >= 6)):
            raise ValueError('Invalid sampling frequencies/settings')
        if len(values.capacitors_pf_by_setting[0]) != len(self.capacitor_edges):
            raise ValueError('Capacitor count does not match topology')
        K, _ = self.matrices(values)  # unchanged complete SPD check
        Y = np.broadcast_to(K, (omega.size, self.inductor_tree.node_count,
                               self.inductor_tree.node_count)).copy() / (omega[:, None, None] * 1e-9)
        C = np.asarray(values.capacitors_pf_by_setting, dtype=float)
        B = incidence_matrix(self.capacitor_edges, self.inductor_tree.node_count)
        coeff = C * 1e-12 / (1 / np.asarray(self.capacitor_q)[None, :] - 1j)
        if self.variant == 'six':
            D = np.einsum('sb,ib,jb->sij', coeff, B, B, optimize=True)
        else:
            # Stamp order fixed, variable, IC-fixed, constant. Parallel Q60/Q35
            # stay distinct columns; fixed values are recomputed each forward.
            first = self.schema.n_fixed
            last = first + self.schema.n_variable
            fixed = np.r_[np.arange(first), np.arange(last, B.shape[1])]
            var = slice(first, last)
            common = np.einsum('b,ib,jb->ij', coeff[0, fixed], B[:, fixed], B[:, fixed], optimize=True)
            D = common + np.einsum('sb,ib,jb->sij', coeff[:, var], B[:, var], B[:, var], optimize=True)
        Y += omega[:, None, None] * D[setting]
        if not np.all(np.isfinite(Y)):
            raise CircuitNumericalError('node_nonfinite', 'Non-finite nodal admittance',
                sample_index=int(np.flatnonzero(~np.all(np.isfinite(Y), axis=(1, 2)))[0]))
        return Y


def probe_model(model, variant):
    if variant == 'baseline':
        return model
    if variant not in ('six', 'split'):
        raise ValueError('Unknown diagnostic variant')
    t = model.topology
    topology = ProbeTopology(t.inductor_tree, t.coupling_pairs, t.inductor_q,
                             t.capacitor_edges, t.capacitor_q, model.schema, variant)
    return replace(model, topology=topology)


def main():
    import benchmark_minimal_worker as bench
    from lpf.search import _worker_next as wn
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--variant', choices=('baseline', 'six', 'split'), required=True)
    args, remaining = parser.parse_known_args()
    if args.variant != 'baseline' and any(v == 'deep' for v in remaining):
        parser.error('Probe overrides node_admittance: base-class deep probes would miss it; use plain/timed')
    build = wn.build_rf_model
    stream = io.StringIO()
    with patch.object(wn, 'build_rf_model', lambda *a, **k: probe_model(build(*a, **k), args.variant)), \
            patch.object(sys, 'argv', [str(ROOT / 'scripts/benchmark_minimal_worker.py'), *remaining]), \
            redirect_stdout(stream):
        bench.main()
    report = json.loads(stream.getvalue())
    report['issue410'] = dict(variant=args.variant,
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
