"""Regression against existing Phase 2 L/C/Q checkpoints; no EM guarantee."""
import csv
import json
import unittest
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'experiments/chatgpt_topology_search/loss_decomposition.py'
spec=importlib.util.spec_from_file_location('loss_decomposition',MODULE)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class PowerBudget(unittest.TestCase):
    def test_two_tunable_35db_reference(self):
        d=json.loads((ROOT/'candidates/LPF-007.json').read_text())
        normalized=mod.normalize(d)
        with (ROOT/'data/bands.csv').open() as fh: bands=list(csv.DictReader(fh))
        a=mod.analyze(normalized,bands,n=201)
        w=a['worst_passband']
        self.assertAlmostEqual(w['total_IL_dB'],d.get('performance',{}).get('worst_IL_db',0.5131684137962829),places=6)
        self.assertAlmostEqual(w['total_IL_dB'],w['reflection_dB']+w['absorbed_network_dissipation_dB'],places=10)
        self.assertLess(abs(w['power_residual_W']),1e-12)

    def test_three_tunable_with_pcb_pattern_cap(self):
        p=ROOT/'experiments/chatgpt_topology_search/runs/EXP-010/EXP010-05.json'
        d=json.loads(p.read_text());n=mod.normalize(d)
        with (ROOT/'data/bands.csv').open() as fh: bands=list(csv.DictReader(fh))
        a=mod.analyze(n,bands,n=201)
        w=a['worst_passband']
        self.assertAlmostEqual(w['total_IL_dB'],d['verified_dense_metrics']['worst_IL_db'],places=6)
        self.assertEqual(a['component_counts']['PCB_PATTERN_C'],1)
        self.assertEqual(a['component_counts']['IC_VARIABLE_C'],3)
        self.assertAlmostEqual(w['total_IL_dB'],w['reflection_dB']+w['inductor_dissipation_dB_allocated']+w['GJM01_dissipation_dB_allocated']+w['IC_variable_C_dissipation_dB_allocated']+w['PCB_C_dissipation_dB_allocated'],places=10)
        self.assertLess(abs(w['power_residual_W']),1e-12)

if __name__ == '__main__':unittest.main()