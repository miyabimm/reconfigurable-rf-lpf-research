#!/usr/bin/env python3
"""Issue #413 opt-in precomputed C stamps; never installed in production."""
import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
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
from lpf.rf_core.coupled_lc import CoupledLCTopology, CircuitValues
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.topology_management.circuit_layout import incidence_matrix

VARIANTS = ('six-matmul', 'direct-matmul', 'six-einsum-no-opt')


@dataclass(frozen=True)
class ProbeTopology(CoupledLCTopology):
    variant: str
    stamps: np.ndarray = field(init=False, repr=False, compare=False)
    flat: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        super().__post_init__()
        if self.variant not in VARIANTS:
            raise ValueError('Unknown diagnostic variant')
        b = incidence_matrix(self.capacitor_edges, self.inductor_tree.node_count).T
        t = (1e-12 / (1 / np.asarray(self.capacitor_q) - 1j))[:, None, None] * b[:, :, None] * b[:, None, :]
        # Topology/Q only; no candidate C or L/k cache. Preserve every branch,
        # including ground and parallel branches with unequal Q, in schema order.
        t = np.frombuffer(t.tobytes(), dtype=complex).reshape(t.shape)
        object.__setattr__(self, 'stamps', t)
        object.__setattr__(self, 'flat', t.reshape(len(b), self.inductor_tree.node_count**2))

    def node_admittance(self, values, omega_rad_s, setting_indices):
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
        K, _ = self.matrices(values)
        n = self.inductor_tree.node_count
        Y = np.broadcast_to(K, (omega.size, n, n)).copy() / (omega[:, None, None] * 1e-9)
        C = np.asarray(values.capacitors_pf_by_setting, dtype=float)
        if self.variant == 'direct-matmul':
            D = (C[setting] @ self.flat).reshape(omega.size, n, n)
        elif self.variant == 'six-matmul':
            D = (C @ self.flat).reshape(6, n, n)[setting]
        else:
            D = np.einsum('sb,bij->sij', C, self.stamps, optimize=False)[setting]
        Y += omega[:, None, None] * D
        if not np.all(np.isfinite(Y)):
            raise CircuitNumericalError('node_nonfinite', 'Non-finite nodal admittance',
                sample_index=int(np.flatnonzero(~np.all(np.isfinite(Y), axis=(1, 2)))[0]))
        return Y


def probe_model(model, variant):
    if variant == 'baseline':
        return model
    t = model.topology
    return replace(model, topology=ProbeTopology(t.inductor_tree, t.coupling_pairs,
        t.inductor_q, t.capacitor_edges, t.capacitor_q, variant))


def main():
    import benchmark_minimal_worker as bench
    from lpf.search import _worker_next as wn
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--variant', choices=('baseline', *VARIANTS), required=True)
    args, remaining = parser.parse_known_args()
    if args.variant != 'baseline' and 'deep' in remaining:
        parser.error('Base-class deep probes miss this override; use plain/timed')
    build = wn.build_rf_model
    stream = io.StringIO()
    with patch.object(wn, 'build_rf_model', lambda *a, **k: probe_model(build(*a, **k), args.variant)), \
            patch.object(sys, 'argv', [str(ROOT / 'scripts/benchmark_minimal_worker.py'), *remaining]), \
            redirect_stdout(stream):
        bench.main()
    report = json.loads(stream.getvalue())
    report['issue413'] = dict(variant=args.variant,
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
