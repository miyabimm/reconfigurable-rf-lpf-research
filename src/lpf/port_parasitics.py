"""Fixed, precomputed Touchstone 2-ports used by RF-F003 and its trials.

The optimizer must evaluate the complete external-port cascade. This module
provides reusable data and transmission-chain primitives. It does *not*
silently change historical RF-F001/F002 circuit evaluators.
"""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

import numpy as np

from .constraint_versions import rf_input_file

ROOT = Path(__file__).resolve().parents[2]
Z0 = 50.0


def _file_under_repo(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative:
        raise ValueError("Missing parasitic S2P path")
    if not relative.startswith("data/parasitics/"):
        raise ValueError("Expected registered fixed S2P path")
    return rf_input_file(root, relative)


@lru_cache(maxsize=8)
def _load_verified(path_string, expected_sha256, expected_points,
                   start_hz, stop_hz, step_hz):
    """Load/validate once per process and cache the frozen 2-port."""
    path = Path(path_string)
    content = path.read_bytes()
    actual = sha256(content).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Parasitic S2P SHA256 mismatch: " + str(path))

    lines = content.decode("ascii").splitlines()
    option = [line.strip() for line in lines if line.lstrip().startswith("#")]
    if option != ["# Hz S RI R 50"]:
        raise ValueError("Expected frozen Touchstone 50-ohm RI encoding")

    data = np.loadtxt(path, comments=("!", "#"), dtype=float)
    if data.shape != (expected_points, 9) or not np.all(np.isfinite(data)):
        raise ValueError("Invalid fixed parasitic S2P array shape/values")
    freqs = data[:, 0]
    expect = np.arange(expected_points, dtype=float) * step_hz + start_hz
    if not np.array_equal(freqs, expect) or expect[-1] != stop_hz:
        raise ValueError("Fixed S2P frequency grid mismatch")

    # Touchstone v1 2-port ordering: S11, S21, S12, S22.
    pairs = data[:, 1::2] + 1j * data[:, 2::2]
    s = np.empty((expected_points, 2, 2), dtype=complex)
    s[:, 0, 0] = pairs[:, 0]
    s[:, 1, 0] = pairs[:, 1]
    s[:, 0, 1] = pairs[:, 2]
    s[:, 1, 1] = pairs[:, 3]
    if not np.allclose(s[:, 1, 0], s[:, 0, 1], atol=1e-10, rtol=0):
        raise ValueError("Frozen parasitic 2-port not reciprocal")
    sv = np.linalg.svd(s, compute_uv=False)
    if np.any(sv[:, 0] > 1 + 1e-8):
        raise ValueError("Frozen parasitic 2-port is not passive")
    freqs.flags.writeable = False
    s.flags.writeable = False
    return freqs, s


def get_two_port_s(policy, role, f_hz, *, root=ROOT):
    """Read the RF-F003 fixed S network, no RLC recomputation.

    role: 'input_parasitic' or 'output_parasitic'
    """
    if not np.isfinite(f_hz):
        raise ValueError("Non-finite frequency")
    cfg = policy["external_port_parasitics"]
    if role not in ("input_parasitic", "output_parasitic"):
        raise ValueError("Unknown parasitic role")
    spec = cfg[role]
    opt = cfg["format"]
    if opt["header"] != "# Hz S RI R 50" or opt["z0_ohms"] != Z0:
        raise ValueError("Unsupported S2P normalization")
    freqs, s = _load_verified(
        str(_file_under_repo(root, spec["path"])), spec["sha256"],
        int(opt["points"]), float(opt["f_start_hz"]),
        float(opt["f_stop_hz"]), float(opt["f_step_hz"])
    )
    f = float(f_hz)
    if f < freqs[0] or f > freqs[-1]:
        raise ValueError("S2P extrapolation is prohibited")
    i = int(np.searchsorted(freqs, f))
    if i == 0:
        return s[0].copy()
    if i < len(freqs) and freqs[i] == f:
        return s[i].copy()
    prev = i - 1
    alpha = (f - freqs[prev]) / (freqs[i] - freqs[prev])
    return ((1-alpha) * s[prev] + alpha * s[i]).copy()


def s_to_abcd(s, zref=Z0):
    """ABCD convention [V1,I1] = T @ [V2,-I2]; S normalized to zref."""
    s11, s12 = s[0, 0], s[0, 1]
    s21, s22 = s[1, 0], s[1, 1]
    if abs(s21) < 1e-14:
        raise ValueError("S21 too close to zero for stable ABCD")
    denom = 2*s21
    a = ((1+s11)*(1-s22)+s12*s21)/denom
    b = zref*((1+s11)*(1+s22)-s12*s21)/denom
    c = ((1-s11)*(1-s22)-s12*s21)/(zref*denom)
    d = ((1-s11)*(1+s22)+s12*s21)/denom
    return np.array([[a,b],[c,d]], dtype=complex)


def external_cascade_abcd(policy, f_hz, lpf_abcd, *, root=ROOT):
    """Return external-input-to-output chain matrix for the given LPF."""
    lpf = np.asarray(lpf_abcd, dtype=complex)
    if lpf.shape != (2,2) or not np.all(np.isfinite(lpf)):
        raise ValueError("Expected finite 2x2 LPF ABCD matrix")
    return (s_to_abcd(get_two_port_s(policy, "input_parasitic", f_hz, root=root))
            @ lpf
            @ s_to_abcd(get_two_port_s(policy, "output_parasitic", f_hz, root=root)))


def external_transducer_gain(policy, f_hz, lpf_abcd, *, root=ROOT):
    """Power delivered to full external load / available source power."""
    t = external_cascade_abcd(policy, f_hz, lpf_abcd, root=root)
    src = complex(policy["source_ohms"]["real"], policy["source_ohms"]["imag"])
    load = complex(policy["load_ohms"]["real"], policy["load_ohms"]["imag"])
    a,b,c,d = t[0,0],t[0,1],t[1,0],t[1,1]
    denom = a*load+b+src*(c*load+d)
    if denom == 0:
        raise ValueError("Singular complete cascade")
    return float((4*src.real*load.real) / abs(denom)**2)
