import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'experiments'/'matching_limit'))

from coverage_sampler import sample_graphs
from enumerate_grounded import enumerate_grounded
from instantiate_graph import build_grounded_settings,check_graph
from lpf.constraint_versions import load_constraint
from lpf.evaluate import CASES
from p4_batch import settings_for, validate as validate_search_result
from lpf.evaluate import load_bands


class ExplicitSeriesSearchTests(unittest.TestCase):
    def test_legacy_sampler_keeps_alias_and_new_samplers_label_series(self):
        old,_=sample_graphs(max_internal=1,attempts_per_cell=80,seed=44)
        self.assertTrue(all(t!='LQP02HQ' for g in old for _,_,t in g[1]))
        for mode,expected in (('HV','LQP02HV'),('HQ','LQP02HQ'),
                              ('both',None)):
            graphs,_=sample_graphs(max_internal=1,attempts_per_cell=300,
                                   seed=44,series_mode=mode)
            types={t for g in graphs for _,_,t in g[1]}
            self.assertNotIn('LQP02',types)
            if expected:
                self.assertIn(expected,types)
        counts,graphs=enumerate_grounded(0,2,500,series_mode='both')
        self.assertTrue(graphs)
        self.assertTrue(all(t!='LQP02' for _,edges in graphs for _,_,t in edges))
        with self.assertRaises(ValueError):
            check_graph((3,((1,2,'LQP02'),)),require_explicit_series=True)

    def test_series_bounds_and_three_variable_dimensions(self):
        graph=(4,((1,3,'LQP02HV'),(3,2,'LQP02HQ')))
        from lpf.topology_management import CircuitDefinition
        from lpf.rf_core import build_rf_model
        from lpf.topology_management.circuit_layout import InductorTree, CapacitorPlacement
        from lpf.search.component_constraints import physical_bounds
        policy=load_constraint('RF-T005',allow_trial=True)
        definition = CircuitDefinition(InductorTree(3, ((0,1),(1,2))),
            ('LQP02HV','LQP02HQ'), (0,1), (),
            CapacitorPlacement(3, (), ((0,-1),(1,-1),(2,-1))), (), ('shunt_to_ground',)*3)
        circuit = build_rf_model(definition, policy)
        np.testing.assert_allclose(physical_bounds(definition, circuit.schema, policy),
                                   [(0.4,27),(0.2,56)]+[(0,3)]*18)
        layout={'edges':((3,0),(1,0),(2,0)), 'roles':(None,None,None)}
        x=np.array([2.0,27.0]+[0.5]*18)
        settings=settings_for(graph,x,np.eye(2),variable_layout=layout,
                              resolved_policy=policy,require_explicit_series=True)
        self.assertEqual(set(settings),set(CASES))
        self.assertEqual(len(settings['B71']['capacitors']),3)
        self.assertEqual([l.q for l in settings['B71']['inductors']],[25,20])
        self.assertEqual([c.value for c in settings['B71']['capacitors']],
                         [0.5e-12]*3)


class SearchIndependentValidationTests(unittest.TestCase):
    def test_optimizer_validation_uses_all_three_formulations(self):
        graph=(6,((1,3,'LQP02HV'),(3,2,'LQP02HQ'),
                  (3,4,'LQP02HV'),(3,5,'GJM01')))
        layout={'edges':((4,0),(5,0),(1,3)),
                'roles':(None,None,'bridge')}
        policy=load_constraint('RF-T005',allow_trial=True)
        x=np.asarray([1.8,35.0,2.2,.7]+[.5]*18)
        result=validate_search_result(
            graph,x,np.eye(3),load_bands(),3,variable_layout=layout,
            resolved_policy=policy,require_explicit_series=True)
        self.assertEqual(result['formulations_compared'],[
            'main_augmented_MNA','independent_nodal_admittance','branch_current_MNA'])
        self.assertLess(result['max_gain_mismatch'],1e-10)
        self.assertLess(result['max_power_residual'],1e-12)
        self.assertGreater(result['min_inductance_eigenvalue'],0)

    def test_optimizer_validation_compares_instantiated_edges_to_graph_source(self):
        graph=(4,((1,3,'LQP02HV'),(3,2,'LQP02HQ')))
        layout={'edges':((3,0),(1,0)), 'roles':(None,None)}
        policy=load_constraint('RF-F003')
        original=build_grounded_settings

        def wrong_connections(*args,**kwargs):
            settings=original(*args,**kwargs)
            for params in settings.values():
                parts=list(params['inductors'])
                parts[0]=replace(parts[0],b=2)
                params['inductors']=tuple(parts)
            return settings

        with patch('p4_batch.build_grounded_settings',side_effect=wrong_connections):
            with self.assertRaisesRegex(ValueError,'Inductor connection map'):
                validate_search_result(
                    graph,np.asarray([1.8,2.4]+[.5]*12),np.eye(2),
                    load_bands(),3,variable_layout=layout,
                    resolved_policy=policy,require_explicit_series=True)


if __name__=="__main__":
    unittest.main()
