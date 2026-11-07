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
from enumerate_grounded import count_variable_layouts,enumerate_grounded
from instantiate_graph import build_grounded_settings,check_graph
from lpf.constraint_versions import load_constraint
from lpf.evaluate import CASES
from search_space import enumerate_variable_c_layouts
from coupling_layout import (admissible_matrix,adjacent_patterns,
                             validate_coupling_matrix)
from functools import partial
# Numerical/physical checks use current RF only, not retired execution IDs.
historical=load_constraint('RF-F003')
admissible_matrix=partial(admissible_matrix,resolved_policy=historical)
adjacent_patterns=partial(adjacent_patterns,resolved_policy=historical)
validate_coupling_matrix=partial(validate_coupling_matrix,resolved_policy=historical)
from p4_batch import bounds_for,settings_for,validate as validate_search_result
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
        from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
        from lpf.topology_management.circuit_layout import InductorTree, CapacitorPlacement
        from lpf.search.component_constraints import physical_bounds
        policy=load_constraint('RF-T005',allow_trial=True)
        definition = CircuitDefinition(InductorTree(3, ((0,1),(1,2))),
            ('LQP02HV','LQP02HQ'), (0,1), (),
            CapacitorPlacement(3, (), ((0,-1),(1,-1),(2,-1))), (), ('shunt_to_ground',)*3)
        circuit = build_nominal_circuit(policy, definition)
        np.testing.assert_allclose(physical_bounds(definition, circuit.schema, policy),
                                   [(0.4,27),(0.2,56)]+[(0,3)]*18)
        layout={'edges':((3,0),(1,0),(2,0)),
                'roles':(None,None,None)}
        x=np.array([2.0,27.0]+[0.5]*18)
        settings=settings_for(graph,x,np.eye(2),variable_layout=layout,
                              resolved_policy=policy,require_explicit_series=True)
        self.assertEqual(set(settings),set(CASES))
        self.assertEqual(len(settings['B71']['capacitors']),3)
        self.assertEqual([l.q for l in settings['B71']['inductors']],[25,20])
        self.assertEqual([c.value for c in settings['B71']['capacitors']],
                         [0.5e-12]*3)


class PolicyLayoutEnumerationTests(unittest.TestCase):
    def setUp(self):
        # Ground=0, input=1, output=2, internal nodes=3,4.
        self.graph=(5,((1,3,'LQP02HV'),(3,2,'LQP02HQ'),
                       (3,4,'LQP02HV')))

    def test_formal_layouts_include_internal_nodes_and_closed_count_limit(self):
        policy=load_constraint('RF-F003')
        layouts=enumerate_variable_c_layouts(self.graph,policy)
        self.assertTrue(layouts)
        self.assertTrue(all(1 <= len(row['edges']) <= 2 for row in layouts))
        self.assertTrue(any(all(b==0 for _,b in row['edges']) for row in layouts))
        self.assertTrue(any((3,0) in row['edges'] or (4,0) in row['edges']
                            for row in layouts))
        capped=enumerate_variable_c_layouts(self.graph,policy,max_layouts=3)
        indices=[round(i*(len(layouts)-1)/2) for i in range(3)]
        self.assertEqual(capped,[layouts[index] for index in indices])
        self.assertEqual(count_variable_layouts(
            self.graph,'RF-F003',max_layouts=2),2)

    def test_current_three_branch_trials_layout_shapes_and_bridge_bypass(self):
        t1=load_constraint('RF-T005',allow_trial=True)
        t2=load_constraint('RF-T007',allow_trial=True)
        layouts1=enumerate_variable_c_layouts(self.graph,t1)
        layouts2=enumerate_variable_c_layouts(self.graph,t2)
        self.assertTrue(layouts1)
        self.assertTrue(layouts2)
        self.assertTrue(all(1 <= len(x['edges']) <= 3 for x in layouts1))
        self.assertTrue(any(sum(role=='bridge' for role in x['roles'])==1
                            and sum(0 in edge for edge in x['edges'])==2
                            for x in layouts2))
        self.assertTrue(any(any(a>=3 or b>=3 for a,b in x['edges'][:2])
                            for x in layouts2))

    def test_bridge_cannot_be_the_only_fixed_signal_path(self):
        policy=load_constraint('RF-T005',allow_trial=True)
        broken=(5,((1,3,'LQP02HV'),(3,4,'LQP02HQ'),(4,0,'GJM01')))
        # This graph itself lacks a fixed input-to-output connection and cannot
        # provide a bridge layout that bypasses a series-only variable C.
        layouts = enumerate_variable_c_layouts(broken,policy)
        # Current trials also enumerate series/shunt proposals, but must not
        # label a new signal-path closure as an already-fixed-path bridge.
        self.assertTrue(layouts)
        self.assertTrue(all('bridge' not in row['roles'] for row in layouts))


class CouplingPhysicalAdjacencyTests(unittest.TestCase):
    def test_explicit_series_are_chip_inductors_and_nonneighbors_cannot_be_strong(self):
        types=['LQP02HV','LQP02HQ','LQP02HV']
        with self.assertRaisesRegex(ValueError,'Invalid coupling'):
            admissible_matrix(types,[2e-9]*3,
                              chip_edges={frozenset((0,2)):.2})
        k=np.eye(3);k[0,2]=k[2,0]=.2
        with self.assertRaisesRegex(ValueError,'physical neighbors'):
            validate_coupling_matrix(types,[2e-9]*3,k)
        good=admissible_matrix(types,[2e-9]*3,
                               chip_edges={frozenset((0,1)):.1})
        self.assertAlmostEqual(good[0,1],.1)
        self.assertTrue(any(pattern.get(frozenset((0,1)))==.1
                            for pattern in adjacent_patterns(types)))


    def test_nominal_nonstrong_zero_and_explicit_sensitivity_only(self):
        limits=load_constraint('RF-F003')['coupling_limits']
        self.assertEqual(limits['chip_chip_nonstrong_nominal_k'],0)
        self.assertEqual(limits['chip_chip_nonstrong_abs_k_max'],.03)
        types=['LQP02HV','LQP02HQ','LQP02HV']
        values=[1e-9,2e-9,3e-9]
        self.assertTrue(validate_coupling_matrix(types,values,np.eye(3)))
        for value in (.01,-.01,.03,-.03):
            with self.subTest(k=value):
                matrix=np.eye(3)
                matrix[0,2]=matrix[2,0]=value
                with self.assertRaisesRegex(ValueError,'physical neighbors'):
                    validate_coupling_matrix(types,values,matrix)
                self.assertTrue(validate_coupling_matrix(
                    types,values,matrix,nominal=False))
        k=np.eye(3);k[0,2]=k[2,0]=.03001
        with self.assertRaisesRegex(ValueError,'physical neighbors'):
            validate_coupling_matrix(types,values,k,nominal=False)
        k=np.eye(3);k[0,1]=k[1,0]=.1
        self.assertTrue(validate_coupling_matrix(types,values,k))
        with self.assertRaisesRegex(ValueError,'nominal must'):
            validate_coupling_matrix(types,values,k,nominal='false')



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
