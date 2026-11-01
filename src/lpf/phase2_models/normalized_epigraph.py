"""Opt-in affine coordinates for C1; no RF or scheduling changes.

Physical variables with finite nonzero-width bounds map to [0, 1]. Fixed
variables remain present at coordinate zero (bound [0, 0]); unbounded physical
variables are rejected. The final epigraph remains unbounded, in dB. No clip,
open-bound epsilon, projection, component repair or feasibility recovery.
"""
import numpy as np

from .problem_seed import VectorBox


class NormalizedEpigraph:
    def __init__(self, problem):
        self.physical = problem
        bounds = np.asarray(problem.box.bounds[:-1], dtype=float)
        if (bounds.shape != (problem.circuit.schema.vector_length, 2)
                or not np.all(np.isfinite(bounds))
                or np.any(bounds[:, 1] < bounds[:, 0])):
            raise ValueError('Normalization requires finite ordered physical bounds')
        self.lower = bounds[:, 0].copy()
        width = bounds[:, 1] - bounds[:, 0]
        self.fixed = width == 0
        self.scale = np.where(self.fixed, 1., width)
        self.box = VectorBox(tuple((0., 0. if fixed else 1.) for fixed in self.fixed)
                             + ((None, None),), problem.box.open_lower)

    def _check(self, vector, box):
        x = np.asarray(vector, dtype=float)
        if x.shape != (len(box.bounds),) or not np.all(np.isfinite(x)):
            raise ValueError('Expected complete finite vector plus epigraph dB')
        if any((lo is not None and v < lo) or (hi is not None and v > hi)
               for v, (lo, hi) in zip(x, box.bounds)):
            raise ValueError('Vector outside coordinate box')
        if any(x[i] <= box.bounds[i][0] for i in box.open_lower):
            raise ValueError('Excluded open lower bound')
        return x

    def to_normalized(self, vector):
        x = self._check(vector, self.physical.box)
        self.physical.circuit.validate_components(x[:-1])
        return np.r_[(x[:-1] - self.lower) / self.scale, x[-1]]

    def to_physical(self, vector):
        z = self._check(vector, self.box)
        x = np.r_[self.lower + self.scale * z[:-1], z[-1]]
        self._check(x, self.physical.box)
        self.physical.circuit.validate_components(x[:-1])
        return x

    def objective(self, vector):
        return self.physical.objective(self.to_physical(vector))

    def residuals(self, vector):
        return self.physical.residuals(self.to_physical(vector))
