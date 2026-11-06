"""Retired schema1 fixture builder; never imported by schema2 develop.

Kept only for the old fixture command/tests, pending their bounded removal.
This is not a supported research execution or compatibility contract.
"""
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import build_nominal_circuit
from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement


def build(definition, rf):
    if (not isinstance(rf, dict) or type(rf.get('allow_trial')) is not bool or
            set(rf) != {'id', 'effective_sha256', 'allow_trial'} or
            rf['id'] != 'RF-T008' or rf['allow_trial'] is not True):
        raise ValueError('Explicit RF-T008 rev3 opt-in and effective SHA required')
    d = dict(definition)
    d['inductor_tree'] = InductorTree(**d['inductor_tree'])
    d['capacitor_placement'] = CapacitorPlacement(**d['capacitor_placement'])
    c = build_nominal_circuit(load_constraint('RF-T008', allow_trial=True), CircuitDefinition(**d))
    if c.policy_fingerprint != rf['effective_sha256']:
        raise ValueError('Resolved RF SHA mismatch')
    return c
