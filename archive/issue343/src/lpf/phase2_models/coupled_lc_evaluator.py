"""Legacy sampled ABCD evaluator; not used by the schema2 RF core."""
import numpy as np
from lpf.rf_core._grid import CASES
from lpf.phase2_models._grid import SampledExternalEvaluator
from lpf.rf_core.coupled_lc import CircuitValues, CoupledLCTopology, ParameterVectorSchema, _fixed_port_impedance
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class CoupledLCEvaluator(SampledExternalEvaluator):
    """Phase-2 sampled RF forward evaluator over explicit immutable inputs.

    Samples exactly the grid and frozen S2P in SampledExternalEvaluator.
    Neither the RF constraint nor the independent MNA is implicitly proven.
    """

    def __init__(self, policy, points, topology, schema, *, extra_frequencies=()):
        if not isinstance(topology, CoupledLCTopology):
            raise TypeError("Expected CoupledLCTopology")
        if not isinstance(schema, ParameterVectorSchema):
            raise TypeError("Expected ParameterVectorSchema")
        if (schema.n_inductors != len(topology.inductor_tree.edges) or
                schema.n_coupling != len(topology.coupling_pairs) or
                schema.capacitor_count != len(topology.capacitor_edges)):
            raise ValueError("Circuit schema and topology disagree")
        self.topology = topology
        self.schema = schema
        self.source_ohms = _fixed_port_impedance(policy, "source_ohms")
        self.load_ohms = _fixed_port_impedance(policy, "load_ohms")
        super().__init__(policy, points, extra_frequencies=extra_frequencies)

    def il(self, vector):
        if isinstance(vector, CircuitValues):
            # A typed value is not an escape hatch for cross-setting changes
            # to fixed/IC-fixed/constant C or topology dimension mismatches.
            self.schema.encode(vector)
            values = vector
        else:
            values = self.schema.decode(vector)
        R = self.topology.port_admittance(values, self.omega, self.setting)
        a, b, c, d = R[:, 0, 0], R[:, 0, 1], R[:, 1, 0], R[:, 1, 1]
        bad_transfer = np.flatnonzero(np.abs(c) < 1e-21)
        if bad_transfer.size:
            raise CircuitNumericalError(
                "transfer_singular", "Transfer admittance is singular",
                sample_index=int(bad_transfer[0])
            )
        t = np.empty((len(self.f), 2, 2), complex)
        t[:, 0, 0] = -d / c
        t[:, 0, 1] = -1 / c
        t[:, 1, 0] = -(a * d - b * c) / c
        t[:, 1, 1] = -a / c
        if not np.all(np.isfinite(t)):
            raise CircuitNumericalError("abcd_nonfinite", "Non-finite LPF ABCD")
        full = self.pre @ t @ self.post
        if not np.all(np.isfinite(full)):
            raise CircuitNumericalError(
                "cascade_nonfinite", "Non-finite external S2P + LPF cascade"
            )
        zl, zs = self.load_ohms, self.source_ohms
        den = full[:, 0, 0] * zl + full[:, 0, 1] + zs * (
            full[:, 1, 0] * zl + full[:, 1, 1]
        )
        if not np.all(np.isfinite(den)) or np.any(den == 0):
            raise CircuitNumericalError(
                "gain_denominator_invalid", "Non-finite or zero cascade denominator"
            )
        gain = 4 * zs.real * zl.real / np.abs(den) ** 2
        if not np.all(np.isfinite(gain)):
            raise CircuitNumericalError("gain_nonfinite", "Non-finite transfer gain")
        il = -10 * np.log10(np.maximum(gain, 1e-300))
        if not np.all(np.isfinite(il)):
            raise CircuitNumericalError("il_nonfinite", "Non-finite insertion loss")
        return il

    def summary(self, vector):
        values = vector if isinstance(vector, CircuitValues) else self.schema.decode(vector)
        y = self.il(values)
        critical = []
        for role in (0, 1, 2):
            index = np.flatnonzero(self.role == role)
            critical.append(int(index[np.argmax(y[index])
                                      if role == 0 else np.argmin(y[index])]))
        _, M = self.topology.matrices(values)
        return {
            "worst_IL_db": float(y[critical[0]]),
            "min_H2_db": float(y[critical[1]]),
            "min_H3_db": float(y[critical[2]]),
            "locations": tuple({
                "case": CASES[self.setting[i]],
                "frequency_mhz": float(self.f[i]),
                "segment": int(self.segment[i])
            } for i in critical),
            "min_L_eigenvalue_nH": float(np.linalg.eigvalsh(M)[0]),
        }
