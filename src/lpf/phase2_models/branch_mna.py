"""Independent branch-current MNA for the Phase-2 nominal L/C core.

This is a bare network solver, not external-S2P or RF compliance validation.
For each sample, with oriented incidence B and branch currents I, it solves

    [Yc + Yterm   B] [V] = [injected current]
    [B.T         -Z] [I]   [0]

Z = omega * (diag(L/Q) + j*M), with signed mutual inductances M.
Capacitor admittances are stamped separately, including parallel fixed and
variable branches. No forward nodal, Schur or ABCD matrices are used.
Voltages are peak phasors, currents in amperes; L is nH and C pF. Port
terminations and current injections are explicit and do not attest policy.
"""
import numpy as np

from .api import NominalCircuit
from .circuit_layout import incidence_matrix
from .coupled_lc import CircuitValues
from .numerical_diagnostics import CircuitNumericalError


def solve_branch_mna(circuit, values, frequency_hz, setting, *,
                     injected_currents_a, termination_admittances_s):
    """Solve one sample; return node voltages and oriented L currents.

    Both boundary vectors have one entry per hot node. Termination
    admittances must be passive and referenced to ground. Component-policy
    validation is deliberately separate; this solver is not a promotion gate.
    """
    if not isinstance(circuit, NominalCircuit):
        raise TypeError("Expected NominalCircuit")
    if not isinstance(values, CircuitValues):
        values = circuit.decode(values)
    circuit.encode(values)  # validates dimensions and invariant fixed C
    topology = circuit.topology
    tree = topology.inductor_tree
    n, m = tree.node_count, len(tree.edges)
    if type(setting) is not int or not 0 <= setting < 6:
        raise ValueError("Invalid setting index")
    try:
        f = float(frequency_hz)
        current = np.asarray(injected_currents_a, dtype=complex)
        term = np.asarray(termination_admittances_s, dtype=complex)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid MNA input") from exc
    if (not np.isfinite(f) or f <= 0 or current.shape != (n,) or
            term.shape != (n,) or not np.all(np.isfinite(current)) or
            not np.all(np.isfinite(term)) or np.any(term.real < 0)):
        raise ValueError("Invalid frequency, current or passive termination")

    L = np.asarray(values.inductances_nh) * 1e-9
    mutual = np.diag(L.copy())
    with np.errstate(over="ignore", invalid="ignore"):
        for (a, b), k in zip(topology.coupling_pairs, values.coupling_k):
            mutual[a, b] = mutual[b, a] = k * np.sqrt(L[a] * L[b])
    if not np.all(np.isfinite(mutual)):
        raise CircuitNumericalError("mutual_nonfinite", "Non-finite MNA mutual L matrix")
    try:
        eig = np.linalg.eigvalsh(mutual)
    except np.linalg.LinAlgError as exc:
        raise CircuitNumericalError("mutual_eigensolve_failed", "MNA L eigensolver failed") from exc
    if not np.all(np.isfinite(eig)):
        raise CircuitNumericalError("mutual_nonfinite", "Non-finite MNA L eigenvalues")
    if eig[0] <= eig[-1] * 1e-12:
        raise CircuitNumericalError("mutual_not_spd", "MNA mutual L matrix is not SPD")

    omega = 2 * np.pi * f
    z = omega * (np.diag(L / np.asarray(topology.inductor_q)) + 1j * mutual)
    bc = incidence_matrix(topology.capacitor_edges, n)
    cap = np.asarray(values.capacitors_pf_by_setting[setting]) * 1e-12
    yc = omega * cap / (1 / np.asarray(topology.capacitor_q) - 1j)
    # Scale KCL by 50 ohms and use 50*I as the branch unknown to keep
    # the condition estimate meaningful across voltage and current units.
    scale = 50.0
    matrix = np.zeros((n + m, n + m), dtype=complex)
    matrix[:n, :n] = scale * (np.diag(term) + (bc * yc) @ bc.T)
    b = tree.incidence()
    matrix[:n, n:] = b
    matrix[n:, :n] = b.T
    matrix[n:, n:] = -z / scale
    rhs = np.concatenate((scale * current, np.zeros(m, dtype=complex)))
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(rhs)):
        raise CircuitNumericalError("mna_nonfinite", "Non-finite MNA matrix or RHS")
    try:
        condition = np.linalg.cond(matrix)
        if not np.isfinite(condition) or condition >= 1e12:
            raise CircuitNumericalError("mna_ill_conditioned", "Singular or ill-conditioned MNA matrix")
        solution = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError as exc:
        raise CircuitNumericalError("mna_solve_failed", "MNA solve failed") from exc
    if not np.all(np.isfinite(solution)):
        raise CircuitNumericalError("mna_nonfinite", "Non-finite MNA solution")
    return solution[:n], solution[n:] / scale
