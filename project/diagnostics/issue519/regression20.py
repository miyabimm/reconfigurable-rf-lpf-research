#!/usr/bin/env python3
"""Additional #520 candidate-only regression; production code remains untouched."""
import sys
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import patch
import unittest
import warnings
import numpy as np
from probe import ROOT, activate, restore
sys.path.insert(0, str(ROOT/'tests'))
from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.rf_core.coupled_lc import CoupledLCTopology

MODES=('base','A','B','AB')

class AdditionalRegression(unittest.TestCase):
    def setUp(self):
        _,_,self.model,_,self.x=make('RF-T008')
        self.evaluator=self.model.evaluator(grid(self.model.resolved_policy))

    def tearDown(self): restore()

    def test_no_internal_nodes_projected_real_stamp(self):
        # Principal port submatrix of a real RF-T008 topology; same schema,
        # values, analytic dY and fixed S2P, but exactly two nodal unknowns.
        top=self.model.topology
        class Projected:
            inductor_tree=SimpleNamespace(node_count=2,source_node=0,load_node=1)
            def matrices(self, values): return top.matrices(values)
            def node_admittance(self,*args,**kwargs): return top.node_admittance(*args,**kwargs)[:,:2,:2]
            def node_admittance_with_jacobian(self,values,schema,omega,settings,*,matrices=None,node=None):
                y,dy=top.node_admittance_with_jacobian(values,schema,omega,settings,matrices=matrices)
                return y[:,:2,:2],dy[:,:,:2,:2]
        ev=replace(self.model,topology=Projected()).evaluator(self.evaluator.grid)
        activate('base'); reference,jref=ev.evaluate_with_il_jacobian(self.x)
        for mode in MODES[1:]:
            with self.subTest(mode=mode):
                activate(mode); actual,jac=ev.evaluate_with_il_jacobian(self.x)
                for k in ('s','il_db','apl_db','in_rl_db','out_rl_db'):
                    np.testing.assert_allclose(getattr(actual,k),getattr(reference,k),rtol=1e-12,atol=1e-12)
                np.testing.assert_allclose(jac,jref,rtol=1e-12,atol=1e-12)

    def test_packed_solve_failures_and_nonfinite(self):
        solve=np.linalg.solve
        for mode in MODES:
            activate(mode); total=2 if mode in ('A','AB') else 3
            for target in range(1,total+1):
                for behavior in ('raise','nan'):
                    calls=[]
                    def injected(a,b):
                        if a.ndim==3 and b.ndim==3 and b.shape[-1]==2*len(self.x):
                            calls.append(a.shape)
                            if len(calls)==target:
                                if behavior=='raise': raise np.linalg.LinAlgError('injected')
                                out=solve(a,b); out[:]=np.nan; return out
                        return solve(a,b)
                    with self.subTest(mode=mode,target=target,behavior=behavior), patch('numpy.linalg.solve',side_effect=injected):
                        with warnings.catch_warnings(), self.assertRaises(CircuitNumericalError) as failure:
                            warnings.simplefilter('ignore',RuntimeWarning)
                            self.evaluator.evaluate_with_il_jacobian(self.x)
                        self.assertEqual(failure.exception.code,'sensitivity_solve_failed' if behavior=='raise' else 'sensitivity_nonfinite')
                        self.assertGreaterEqual(len(calls),target)

    def test_nonfinite_and_overflow_nodal_sensitivity(self):
        original=CoupledLCTopology.node_admittance_with_jacobian
        for mode in MODES:
            activate(mode)
            for value in (np.nan,np.inf,1e308):
                def injected(top,*args,**kwargs):
                    y,dy=original(top,*args,**kwargs); dy=dy.copy(); dy[:,0,:,:]=value; return y,dy
                with self.subTest(mode=mode,value=value), patch.object(CoupledLCTopology,'node_admittance_with_jacobian',injected):
                    with warnings.catch_warnings(), self.assertRaises(CircuitNumericalError) as failure:
                        warnings.simplefilter('ignore',RuntimeWarning)
                        self.evaluator.evaluate_with_il_jacobian(self.x)
                    self.assertEqual(failure.exception.code,'sensitivity_nonfinite')

    def test_extreme_cascade_overflow_finite_masks(self):
        from probe import OLD_CASCADE, cascade_one_side
        from lpf.rf_core.model import _cascade
        for eps in (1e-16,1e-100,1e-160,1e-200,1e-300):
            for zero in (False,True):
                a=np.ones((1,2,2),complex); b=np.ones((1,2,2),complex)
                b[0,0,0]=1+1j*eps
                if zero: a[0,0,1]=0
                d=np.ones((1,1,2,2),complex); z=np.zeros_like(d)
                with np.errstate(all='ignore'):
                    self.assertTrue(np.isfinite(_cascade(a,b)).all())
                    for side in ('left','right'):
                        if side=='left': old=OLD_CASCADE(a,z,b,d); new=cascade_one_side(a,None,b,d)
                        else: old=OLD_CASCADE(a,d,b,z); new=cascade_one_side(a,d,b,None)
                        with self.subTest(eps=eps,zero=zero,side=side):
                            np.testing.assert_array_equal(np.isfinite(old),np.isfinite(new))

    def test_candidate_deep_hooks_on_success_and_failure(self):
        from lpf.search._rf_deep_timing import search_rf_timing
        from lpf.rf_core import model,coupled_lc
        from lpf.rf_core.model import RFEvaluator
        from lpf.timing import TimerCollector
        for mode in MODES:
            activate(mode); method=RFEvaluator.evaluate_with_il_jacobian; cascade=model._cascade_jacobian
            for fail in (False,True):
                timer=TimerCollector()
                with self.subTest(mode=mode,fail=fail):
                    try:
                        with search_rf_timing(timer,'search'):
                            if fail:
                                with patch.object(model,'_cascade_jacobian',side_effect=RuntimeError('injected')):
                                    with self.assertRaisesRegex(RuntimeError,'injected'):
                                        self.evaluator.evaluate_with_il_jacobian(self.x)
                            else: self.evaluator.evaluate_with_il_jacobian(self.x)
                    finally:
                        self.assertIs(RFEvaluator.evaluate_with_il_jacobian,method)
                        self.assertIs(model._cascade_jacobian,cascade)
                        self.assertIsNone(model._deep_timing); self.assertIsNone(coupled_lc._deep_timing)

if __name__=='__main__': unittest.main(verbosity=2)
