"""Sequential file-submission Campaign boundary (isolated development only).

No production EXP/G1 approval is manufactured here. The existing development
Worker/raw contract remains explicitly labelled; formal G0/G1/G3-G5 integration
is a separate gate, not a mode switch on this runner.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile

import yaml

from lpf.constraint_versions import load_constraint
from . import controller, runner, starts
from ._job_evaluation import source_identity
from .plan import Plan, ROOT
from .preflight import freeze
from .proposals import load_proposal, normalize_proposal
from .storage import atomic, canonical, plain, sha


def _plan(plan, root):
    if sha(plan.data) != plan.sha256 or sha(freeze(plan.data['config'], root)) != plan.sha256:
        raise ValueError('Campaign Plan/source/RF/grid mismatch')
    config = plan.data['config']
    if 'campaign' not in config or config['definition'] is not None:
        raise ValueError('Campaign requires an envelope, not a pre-frozen topology')
    if len(config['seeds']) != 1 or len(config['arms']) != 1:
        raise ValueError('Campaign v1 supports one fixed seed/arm rule')


def _directory(output, root):
    output = Path(output).resolve()
    if not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or output.is_relative_to(root):
        raise ValueError('Campaign development output must be system tmp outside checkout')
    return output


def begin_development_campaign(plan, output, *, root=ROOT):
    """Freeze an envelope once, not future definitions, starts or JobSpecs."""
    root = Path(root).resolve()
    _plan(plan, root)
    output = _directory(output, root)
    state = dict(kind='campaign_development_only_not_an_EXP', status='ready',
        plan=plan.data, plan_sha256=plan.sha256, source=source_identity(root),
        topologies=[], jobs=[], events=[], proposal_ids=[], requested=0, completed=0,
        reserved=0, independent_requested=0, independent_completed=0,
        gates=plan.data['gates'], preservation_audit='not_run')
    output.mkdir(parents=True, exist_ok=False)
    atomic(output/'campaign.json', state)
    return campaign_snapshot(output)


def campaign_snapshot(output):
    """Return a fresh read-only-by-copy advisor input and its canonical SHA."""
    state = json.loads((Path(output)/'campaign.json').read_bytes())
    envelope = state['plan']['config']['campaign']
    results = []
    for job in state['jobs']:
        evidence = job.get('evidence', {})
        terminal = [b['assessment'] for b in evidence.get('observations', [])
                    if b['stage'] == 'terminal' and b['status'] == 'completed']
        summary = dict(worker_status=job.get('worker_status', 'unknown'),
            exit_reason=job.get('exit_reason'), terminal=evidence.get('terminal', {'status': 'not_run'}),
            terminal_assessments=terminal, dense=evidence.get('dense', {'status': 'not_run'}))
        results.append(dict(job_id=job['job_id'], definition_sha256=job['definition_sha256'],
            status=job['status'], requested=job['requested'], completed=job['completed'],
            result_sha256=job.get('raw_content_sha256'), evidence_sha256=sha(evidence),
            summary_sha256=sha(summary), summary=summary))
    snapshot = dict(plan_sha256=state['plan_sha256'], status=state['status'],
        structure=envelope['structure'], topology_sha256=list(state['topologies']),
        remaining_topologies=envelope['max_topologies']-len(state['topologies']),
        requested=state['requested'], completed=state['completed'], reserved=state['reserved'],
        remaining_rf_samples=envelope['max_rf_samples']-state['requested']-state['reserved'],
        results=results, events_sha256=sha(state['events']))
    return dict(snapshot=snapshot, based_on_state_sha256=sha(snapshot))


def _totals(state):
    for key in ('requested', 'completed', 'reserved', 'independent_requested', 'independent_completed'):
        state[key] = sum(j[key] for j in state['jobs'])
    if state['requested']+state['reserved'] > state['plan']['config']['campaign']['max_rf_samples']:
        raise ValueError('Campaign sample invariant violated')


def _check_ready_state(state, plan, output, root):
    """A new file submission must not trust cached totals or prior raw digests."""
    from .worker import JobSpec
    if state['kind'] != 'campaign_development_only_not_an_EXP' or state['gates'] != plan.data['gates']:
        raise ValueError('Campaign kind/gate identity mismatch')
    proposal_ids = []
    for index, event in enumerate(state['events']):
        if 'input_path' not in event:
            continue
        if event['input_path'] != f'proposal-{index:06d}.yaml':
            raise ValueError('Campaign proposal event/path mismatch')
        original = (output/event['input_path']).read_bytes()
        if hashlib.sha256(original).hexdigest() != event['input_sha256']:
            raise ValueError('Campaign proposal input byte SHA mismatch')
        # Only successfully normalized proposals have an ID. Duplicate-ID
        # rejections retain that ID in events but never register it twice.
        if 'proposal_id' in event and event['proposal_id'] not in proposal_ids:
            proposal_ids.append(event['proposal_id'])
    if proposal_ids != state['proposal_ids']:
        raise ValueError('Campaign proposal ID ledger mismatch')
    topology_shas = []
    accepted = {e['job_id']: e for e in state['events'] if e['status'] == 'accepted'}
    if len(accepted) != len(state['jobs']):
        raise ValueError('Campaign accepted proposal/Job count mismatch')
    for index, row in enumerate(state['jobs']):
        job_id = f'job-{index:06d}'
        spec = JobSpec(**row['spec'])
        data = spec.data
        definition_sha = sha(data['definition'])
        config = plan.data['config']
        config['definition'] = data['definition']
        context = data.get('campaign_context', {})
        event = accepted.get(job_id, {})
        if (row['job_id'] != job_id or row['raw_path'] != job_id+'.json' or
                row['status'] != 'completed' or row['spec_sha256'] != sha(spec) or
                data['source'] != state['source'] or spec.source_sha256 != sha(state['source']) or
                row['campaign_plan_sha256'] != plan.sha256 or
                row['job_plan_sha256'] != spec.plan_sha256 or sha(data['plan']) != spec.plan_sha256 or
                data['plan']['config'] != config or sha(freeze(config, root)) != spec.plan_sha256 or
                row['definition_sha256'] != definition_sha or context.get('job_id') != job_id or
                context.get('plan_sha256') != plan.sha256 or
                context.get('proposal_sha256') != row['proposal_sha256'] or
                event.get('proposal_sha256') != row['proposal_sha256'] or
                event.get('spec_sha256') != sha(spec) or row['cap'] != config['arms'][0]['max_requested_samples']):
            raise ValueError('Campaign durable Job/Plan/proposal identity mismatch')
        if not re.fullmatch(r'proposal-[0-9]{6,}\.yaml', event.get('input_path', '')):
            raise ValueError('Campaign proposal path mismatch')
        proposal_path = output/event['input_path']
        proposal = load_proposal(proposal_path)
        if (hashlib.sha256(proposal_path.read_bytes()).hexdigest() != event['input_sha256'] or
                sha(proposal) != row['proposal_sha256'] or sha(proposal['definition']) != definition_sha or
                context.get('based_on_state_sha256') != proposal['based_on_state_sha256'] or
                context.get('parent_job_id') != (f'job-{index-1:06d}' if index else None)):
            raise ValueError('Campaign preserved proposal/context mismatch')
        if definition_sha not in topology_shas:
            topology_shas.append(definition_sha)
        path = output/row['raw_path']
        imported = runner._development_readback(path, json.loads(path.read_bytes()), spec)
        if not imported['safe_to_release'] or any(row[k] != v for k, v in imported.items()):
            raise ValueError('Campaign prior Worker raw/cost mismatch')
        if row['reserved'] or row['released'] != row['cap']-row['requested']:
            raise ValueError('Campaign released reservation mismatch')
    if topology_shas != state['topologies']:
        raise ValueError('Campaign adopted topology count mismatch')
    expected = copy.deepcopy(state)
    _totals(expected)
    if expected != state:
        raise ValueError('Campaign cached totals mismatch')


def _structure(definition, envelope):
    allowed = envelope['structure']
    if (definition.inductor_tree.node_count > allowed['max_nodes'] or
            len(definition.fixed_c_types) > allowed['max_fixed_capacitors'] or
            len(definition.variable_roles) > allowed['max_variable_capacitors'] or
            not set(definition.inductor_types) <= set(allowed['inductor_types']) or
            not set(definition.fixed_c_types) <= set(allowed['fixed_c_types']) or
            not set(definition.variable_roles) <= set(allowed['variable_roles']) or
            (definition.coupling_pairs and not allowed['allow_coupling']) or
            (definition.capacitor_placement.ic_fixed_edges and not allowed['allow_ic_fixed'])):
        raise ValueError('Structure outside frozen Campaign envelope')


def submit_development_proposal(plan, proposal_path, output, *, root=ROOT, solver_kind='scipy'):
    """One file → one frozen Job → raw readback → next advisor snapshot.

    No auto-retry/resume, no future Job reservations and no autonomous advisor.
    All rejected submissions retain their original bytes and input SHA. Once a
    durable unknown marker exists, storage errors propagate without save retry.
    """
    root = Path(root).resolve()
    output = _directory(output, root)
    ledger = output/'campaign.json'
    state = json.loads(ledger.read_bytes())
    _plan(plan, root)
    if (state['plan_sha256'] != plan.sha256 or state['plan'] != plan.data or
            state['source'] != source_identity(root)):
        raise ValueError('Campaign frozen Plan/source mismatch; STOP')
    if state['status'] != 'ready':
        raise ValueError('Campaign unknown/stopped; no subsequent submission')
    _check_ready_state(state, plan, output, root)
    if solver_kind not in ('scipy', 'fixture'):
        raise ValueError('Unknown solver execution kind')
    original = Path(proposal_path).read_bytes()
    number = len(state['events'])
    evidence = output/f'proposal-{number:06d}.yaml'
    # Never overwrite submission evidence, including after a failed ledger save.
    with evidence.open('xb') as stream:
        stream.write(original)
    event = dict(input_sha256=hashlib.sha256(original).hexdigest(), input_path=evidence.name,
                 status='rejected')
    try:
        proposal = load_proposal(evidence)
        normalized, definition, digest, topology = normalize_proposal(proposal)
        event.update(proposal_id=proposal['proposal_id'], proposal_sha256=digest,
                     definition_sha256=topology, reason=proposal['reason'],
                     based_on_state_sha256=proposal['based_on_state_sha256'])
        if proposal['proposal_id'] in state['proposal_ids']:
            raise ValueError('Duplicate Campaign proposal_id')
        state['proposal_ids'].append(proposal['proposal_id'])
        if proposal['based_on_state_sha256'] != campaign_snapshot(output)['based_on_state_sha256']:
            raise ValueError('Stale Campaign state; request a new proposal')
        envelope = plan.data['config']['campaign']
        _structure(definition, envelope)
        if topology not in state['topologies'] and len(state['topologies']) >= envelope['max_topologies']:
            raise ValueError('Campaign max_topologies exceeded')
        action = controller.topology_action(plan, proposal)
        arm = plan.data['config']['arms'][action.arm_index]
        cap = arm['max_requested_samples']
        if state['requested']+state['reserved']+cap > envelope['max_rf_samples']:
            raise ValueError('Campaign max_rf_samples cannot reserve next Job cap')
        policy = load_constraint(plan.data['config']['rf']['constraint_id'], root=root,
                                 allow_trial=plan.data['config']['rf']['allow_trial'])
        start = starts.generate_for_definition(definition, policy, action.seed)
        # Reuse the exact schema2 plan/compiler and CircuitDefinition data. This
        # per-Job plan is distinct from the G1-style envelope SHA (no self-ref).
        config = plan.data['config']
        config['definition'] = plain(normalized['definition'])
        frozen = freeze(config, root)
        job_plan = Plan(canonical(frozen), sha(frozen))
        independent = envelope['independent']
        # Current fixed Worker validates each terminal top-k candidate. Restrict
        # that count rather than silently running unbounded independent checks.
        if independent['stage'] != 'not_run' and config['selection']['top_k'] > independent['max_candidates']:
            raise ValueError('Independent terminal candidate cap exceeded')
        spots = {} if independent['stage'] == 'not_run' else {'terminal': independent['sample_indices']}
        job_id = f'job-{len(state["jobs"]):06d}'
        context = dict(job_id=job_id,
            parent_job_id=state['jobs'][-1]['job_id'] if state['jobs'] else None,
            plan_sha256=plan.sha256, proposal_sha256=digest,
            based_on_state_sha256=proposal['based_on_state_sha256'])
        spec = runner.freeze_development_job(job_plan, definition, policy, arm['name'], action.seed,
            start['vector'], root=root, spot_checks=spots, campaign_context=context)
        if spec.data['source'] != state['source']:
            raise ValueError('Campaign source changed while freezing Job')
    except (ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        event['rejection_reason'] = f'{type(exc).__name__}: {exc}'
        state['events'].append(event)
        atomic(ledger, state)
        return campaign_snapshot(output)

    # Unique Campaign provenance is frozen inside the reused development spec.
    row = dict(job_id=job_id, worker_job_id=spec.job_id, spec=plain(spec), spec_sha256=sha(spec),
        campaign_plan_sha256=plan.sha256, job_plan_sha256=job_plan.sha256,
        definition_sha256=topology, proposal_sha256=digest, start=plain(start),
        parent_job=state['jobs'][-1]['job_id'] if state['jobs'] else None,
        raw_path=job_id+'.json', status='unknown', cap=cap, requested=0, completed=0,
        reserved=cap, released=0, independent_requested=0, independent_completed=0)
    if topology not in state['topologies']:
        state['topologies'].append(topology)
    event.update(status='accepted', job_id=job_id, spec_sha256=sha(spec))
    state['events'].append(event)
    state['jobs'].append(row)
    state['status'] = 'unknown'
    _totals(state)
    atomic(ledger, state)  # adopt+reserve+unknown is one durable transaction
    try:
        returned = runner.execute_development_job(spec, output/row['raw_path'], root=root,
                                                  solver_kind=solver_kind)
        imported = runner._development_readback(output/row['raw_path'], returned, spec)
    except (Exception, KeyboardInterrupt) as exc:
        # Only add a diagnostic to the already-unknown parent. Never retry a
        # Worker save/forward or release cost on a failed import. Parent atomic
        # failures (including this diagnostic) propagate, with no save retry.
        state['exit_reason'] = f'{type(exc).__name__}: {exc}'
        state['events'].append(dict(status='unknown', job_id=job_id, reason=state['exit_reason']))
        atomic(ledger, state)
        return campaign_snapshot(output)
    candidate = copy.deepcopy(state)
    row = candidate['jobs'][-1]
    row.update(imported)
    row['reserved'] = cap-imported['requested']
    if imported['safe_to_release']:
        row.update(status='completed', reserved=0, released=cap-imported['requested'])
        candidate['status'] = 'ready'
    candidate['events'].append(dict(status=row['status'], job_id=job_id,
        result_sha256=imported['raw_content_sha256'], requested=row['requested'],
        completed=row['completed'], reserved=row['reserved']))
    _totals(candidate)
    atomic(ledger, candidate)  # failure must leave the durable unknown reservation
    return campaign_snapshot(output)


def run_campaign(*args, **kwargs):
    """Formal execution is deliberately fail-closed until G0/G1 is connected."""
    raise ValueError('not_ready: formal Campaign G0/G1 and G3-G5 integration not implemented')
