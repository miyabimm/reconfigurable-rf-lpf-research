"""Frozen target set and crash-safe post-search raw journal.

This is not a G0/G1 gate or a Git evidence exporter. Callers must pass the
existing experiment preflight and storage audits before executing or curating.
An unknown in-progress result is never retried automatically.
"""
from copy import deepcopy
import fcntl
import re
from pathlib import Path

import numpy as np

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from .problem_seed import definition_fingerprint, vector_fingerprint
from .post_search_validation import validate_post_search
from .post_search_evidence import verify_candidate_evidence
from .synthetic_runner import _read


def candidate_binding(candidate_id, circuit, vector, *, optimization_record,
                      source_provenance, budgets, run_dense, run_independent,
                      exchange_record=None, validation_identity=None,
                      validate_terminal_anchor=False, continuation_record=None):
    """Freeze the identity, selection and all limits before validation starts."""
    if not isinstance(candidate_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', candidate_id):
        raise ValueError('Invalid candidate ID')
    if (type(run_dense) is not bool or type(run_independent) is not bool or
            type(validate_terminal_anchor) is not bool):
        raise ValueError('Explicit dense and independent selection required')
    if not isinstance(budgets, dict) or set(budgets) != {
            'separate17', 'dense1001', 'independent_forward84', 'independent_mna84'} or any(
            type(n) is not int or n < 0 for n in budgets.values()):
        raise ValueError('Explicit nonnegative budgets required')
    binding = {'candidate_id': candidate_id, 'policy_id': circuit.policy_id,
            'policy_sha256': circuit.policy_fingerprint,
            'definition_sha256': definition_fingerprint(circuit.definition),
            'vector': np.asarray(vector, float).tolist(), 'vector_sha256': vector_fingerprint(vector),
            'optimization_sha256': canonical_config_hash(optimization_record),
            'exchange_sha256': canonical_config_hash(exchange_record),
            'source_sha256': canonical_config_hash(source_provenance),
            'validation_identity_sha256': canonical_config_hash(validation_identity),
            'budgets': deepcopy(budgets), 'run_dense': run_dense,
            'run_independent': run_independent}
    if validate_terminal_anchor:
        if (not isinstance(continuation_record, dict) or
                not isinstance(continuation_record.get('last_valid_vector'), (list, tuple)) or
                len(continuation_record['last_valid_vector']) != circuit.schema.vector_length + 1 or
                vector_fingerprint(continuation_record['last_valid_vector'][:-1]) != binding['vector_sha256']):
            raise ValueError('Terminal anchor requires matching frozen continuation evidence')
        binding['validate_terminal_anchor'] = True
        binding['continuation_sha256'] = canonical_config_hash(continuation_record)
    elif continuation_record is not None:
        raise ValueError('Continuation evidence requires terminal-anchor mode')
    return binding


def _candidate_status(report):
    """Only explicit check counterexamples are failures; exceptions are not_run."""
    if not isinstance(report, dict) or report.get('schema') != 'post-search-validation-1':
        return {'numerical': 'not_run', 'independent': 'not_run'}
    component = report.get('component', {}).get('state')
    grid17 = report.get('separate17', {}).get('state')
    dense = report.get('dense1001', {}).get('state')
    independent = report.get('independent84', {}).get('state')
    numerical = ('failed' if 'fail' in (component, grid17, dense) else
                 'passed' if (component, grid17, dense) == ('pass', 'pass', 'pass') else 'not_run')
    # Independent can fail independently of numerical aggregation; a candidate
    # not actually reaching MNA is not an independent FAIL.
    mna = ('failed' if independent == 'fail' else
           'passed' if independent == 'pass' and numerical == 'passed' else 'not_run')
    return {'numerical': numerical, 'independent': mna}


def aggregate_selected(candidate_ids, outcomes):
    """Apply PR #268's fixed-set rule independently to both validation levels.

    ``outcomes`` contains only completed journal records, not all search starts.
    A missing or interrupted target is not_run; unexpected IDs are rejected.
    These are validation summaries, not evidence authentication or RF approval.
    """
    if (not isinstance(candidate_ids, list) or len(candidate_ids) != len(set(candidate_ids)) or
            any(not isinstance(c, str) or not c for c in candidate_ids) or not isinstance(outcomes, dict) or
            set(outcomes) - set(candidate_ids)):
        raise ValueError('Invalid frozen selection or unexpected outcome')
    rows = {c: _candidate_status(outcomes.get(c)) for c in candidate_ids}
    result = {}
    for level in ('numerical', 'independent'):
        states = [rows[c][level] for c in candidate_ids]
        result[level] = ('failed' if 'failed' in states else
                         'passed' if states and all(s == 'passed' for s in states) else 'not_run')
    return {'validation': result, 'candidates': rows}


class PostSearchJournal:
    """Single-process raw journal; a failed or interrupted invocation is not retried."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.plan = _read(self.directory / 'selection.json')
        envelope = _read(self.directory / 'run.json')
        if (not isinstance(envelope, dict) or set(envelope) != {'body', 'sha256'} or
                canonical_config_hash(envelope['body']) != envelope['sha256']):
            raise ValueError('Raw journal checksum mismatch')
        self.state = envelope['body']
        if (self.plan.get('schema') != 'post-search-selection-1' or
                self.state.get('selection_sha256') != canonical_config_hash(self.plan)):
            raise ValueError('Frozen selection checksum mismatch')
        targets = self.plan.get('targets')
        if not isinstance(targets, list):
            raise ValueError('Invalid frozen selection')
        self.targets = {row['candidate_id']: row for row in targets}
        if (self.state.get('schema') != 'post-search-journal-1' or len(self.targets) != len(targets) or
                set(self.state['candidates']) != set(self.targets)):
            raise ValueError('Frozen selection/result mismatch')
        running = [k for k, v in self.state['candidates'].items() if v.get('state') == 'running']
        if (any(v.get('state') not in ('not_run', 'running', 'completed') for v in self.state['candidates'].values()) or
                running != ([] if self.state['in_progress'] is None else [self.state['in_progress']])):
            raise ValueError('Invalid or contradictory journal marker')

    @classmethod
    def create(cls, directory, bindings):
        directory = Path(directory)
        if not isinstance(bindings, list) or any(not isinstance(row, dict) for row in bindings):
            raise ValueError('Expected a list of frozen candidate bindings')
        ids = [row.get('candidate_id') for row in bindings]
        if (any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', i) for i in ids)
                or len(ids) != len(set(ids))):
            raise ValueError('Invalid or duplicate candidate IDs')
        # The new directory itself is the durable no-retry marker. If writing
        # fails or the process dies, re-creation must fail and require review.
        directory.mkdir(parents=True, exist_ok=False)
        plan = {'schema': 'post-search-selection-1', 'targets': deepcopy(bindings)}
        state = {'schema': 'post-search-journal-1', 'selection_sha256': canonical_config_hash(plan),
                 'in_progress': None, 'candidates': {i: {'state': 'not_run'} for i in ids}}
        atomic_write_json(directory / 'selection.json', plan, compact=True)
        atomic_write_json(directory / 'run.json',
                          {'body': state, 'sha256': canonical_config_hash(state)}, compact=True)
        return cls(directory)

    def _save(self):
        envelope = {'body': self.state, 'sha256': canonical_config_hash(self.state)}
        atomic_write_json(self.directory / 'run.json', envelope, compact=True)
        actual = _read(self.directory / 'run.json')
        if canonical_config_hash(actual) != canonical_config_hash(envelope):
            raise ValueError('Raw journal readback mismatch')
        self.state = actual['body']

    def summary(self):
        reports = {k: v['report'] for k, v in self.state['candidates'].items()
                   if v.get('state') == 'completed' and 'report' in v}
        return aggregate_selected(list(self.targets), reports)

    def run_candidate(self, candidate_id, circuit, vector, *, optimization_record,
                      source_provenance, budgets, run_dense, run_independent,
                      exchange_record=None, validation_identity=None,
                      validate_terminal_anchor=False, continuation_record=None):
        with (self.directory / 'run.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('Another post-search operation holds the lock') from exc
            return self._run_candidate(candidate_id, circuit, vector,
                optimization_record=optimization_record, source_provenance=source_provenance,
                budgets=budgets, run_dense=run_dense, run_independent=run_independent,
                exchange_record=exchange_record, validation_identity=validation_identity,
                validate_terminal_anchor=validate_terminal_anchor, continuation_record=continuation_record)

    def _run_candidate(self, candidate_id, circuit, vector, *, optimization_record,
                       source_provenance, budgets, run_dense, run_independent,
                       exchange_record=None, validation_identity=None,
                       validate_terminal_anchor=False, continuation_record=None):
        binding = candidate_binding(candidate_id, circuit, vector,
            optimization_record=optimization_record, source_provenance=source_provenance,
            budgets=budgets, run_dense=run_dense, run_independent=run_independent,
            exchange_record=exchange_record, validation_identity=validation_identity,
            validate_terminal_anchor=validate_terminal_anchor, continuation_record=continuation_record)
        # Re-read from disk so another process or accidental edit cannot silently
        # replace the frozen plan or a persisted marker between invocations.
        fresh = type(self)(self.directory)
        if fresh.plan != self.plan or fresh.state != self.state:
            raise ValueError('Journal changed; investigate before continuing')
        if self.state['in_progress'] is not None:
            raise ValueError('Unknown in-progress result; automatic retry prohibited')
        if candidate_id not in self.targets or self.targets[candidate_id] != binding:
            raise ValueError('Candidate differs from frozen selection')
        if self.state['candidates'][candidate_id]['state'] != 'not_run':
            raise ValueError('Candidate already attempted; automatic retry prohibited')
        self.state['in_progress'] = candidate_id
        self.state['candidates'][candidate_id] = {'state': 'running', 'report': None}
        self._save()

        def sink(snapshot):
            self.state['candidates'][candidate_id]['report'] = snapshot
            self._save()

        try:
            result = validate_post_search(circuit, vector, optimization_record=optimization_record,
                source_provenance=source_provenance, budgets=budgets, run_dense=run_dense,
                run_independent=run_independent, exchange_record=exchange_record,
                validation_identity=validation_identity, record_sink=sink,
                validate_terminal_anchor=validate_terminal_anchor)
            verify_candidate_evidence(circuit, binding, result)
        except BaseException:
            # The last durable marker/snapshot remains in-progress. Never write a
            # guessed outcome over it, including on sink/OSError/KeyboardInterrupt.
            raise
        self.state['candidates'][candidate_id] = {'state': 'completed', 'report': result}
        self.state['in_progress'] = None
        self._save()
        return result
