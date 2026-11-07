import copy, hashlib, json, os, tempfile
from pathlib import Path
import yaml
import test_issue325_campaign as ct
import test_issue325_campaign_gates as gt
from lpf.search import campaign, preservation
from lpf.search.storage import sha
from lpf.experiment_manifest import INDEX_FIELDS

# Preserve *all* temporary fixture directories and raw, even on errors.
class PreservedTemporaryDirectory(tempfile.TemporaryDirectory):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._finalizer.detach()
    def cleanup(self): pass

tempfile.TemporaryDirectory = PreservedTemporaryDirectory
class Tiny:
    def setup_model(self, cid='RF-F003', mode='full_lpf', mutate=None):
        def tiny(c):
            c['anytime_samples'] = [56]
            first = c['arms'][0]['steps'][0]
            first['max_requested_samples'] = 56
            first['options'] = dict(max_iterations=1, max_evaluations=1)
            second = copy.deepcopy(first); second['name'] = 'fine'
            c['arms'][0]['steps'].append(second)
            if mutate: mutate(c)
        return super().setup_model(cid, mode, mutate=tiny)
    def setup_campaign(self, max_topologies=1, max_rf_samples=1500, independent=True, cid='RF-F003'):
        return super().setup_campaign(max_topologies=1, max_rf_samples=1500, independent=True, cid=cid)
class Dev(Tiny, ct.CampaignTests): pass
class Formal(Tiny, gt.CampaignGateTests): pass

def check_plan(plan):
    c = plan.data['config']; steps = c['arms'][0]['steps']
    assert c['rf'] == {'constraint_id': 'RF-F003', 'allow_trial': False}
    assert c['campaign']['max_topologies'] == 1 and c['campaign']['max_rf_samples'] == 1500
    assert len(c['seeds']) == len(c['arms']) == 1
    assert c['arms'][0]['max_requested_samples'] == 1500
    assert len(steps) == 2 and all(s['max_requested_samples'] == 56 and s['options'] == {'max_iterations':1,'max_evaluations':1} for s in steps)
    assert c['campaign']['independent'] == {'stage':'terminal','max_candidates':1,'sample_indices':[0]}
    print('PREFLIGHT', json.dumps(c, ensure_ascii=False, sort_keys=True), flush=True)

def inspect(output, plan):
    p = output/'campaign.json'; b = p.read_bytes(); state=json.loads(b)
    print('PARENT_PATH',p, 'SHA256',hashlib.sha256(b).hexdigest(),flush=True)
    print('STATE', json.dumps(state, ensure_ascii=False, sort_keys=True), flush=True)
    assert state['status'] == 'ready', state.get('events')
    assert len(state['jobs']) == len(state['topologies']) == 1
    j = state['jobs'][0]; rp=output/j['raw_path']; rb=rp.read_bytes(); raw=json.loads(rb)
    print('RAW_PATH',rp,'SHA256',hashlib.sha256(rb).hexdigest(),flush=True)
    print('RAW',json.dumps(raw, ensure_ascii=False, sort_keys=True),flush=True)
    assert j['spec_sha256'] == sha(j['spec']) and j['campaign_plan_sha256'] == plan.sha256
    assert j['raw_content_sha256'] == sha(raw)
    assert state['requested'] == state['completed'] > 0 and state['reserved'] == 0
    assert state['independent_requested'] == state['independent_completed'] == 1
    assert j['released'] == 1500-state['requested']
    for g in raw['grids'].values():
        assert len(g['interval_samples']) == 28 and set(g['setting']) == set(range(6))
    assert sum(b['requested'] for b in raw['batches']) == state['requested']
    assert all(b['requested'] == b['completed'] for b in raw['batches'])
    assert raw['batches'][-1]['independent']['status'] == 'pass'
    assert not raw['rf_compliance_certified']
    ev = state['events'][0]; pb=(output/ev['input_path']).read_bytes()
    print('PROPOSAL_PATH',output/ev['input_path'],'SHA256',hashlib.sha256(pb).hexdigest(),flush=True)
    return state, raw

d=Dev(); d.setUp()
plan, definition, out, snap=d.setup_campaign()
check_plan(plan)
proposal=d.proposal(definition,snap)
path=Path(d.raw.name)/'proposal-input.yaml'; path.write_text(yaml.safe_dump(proposal))
print('DEV_ROOT',d.raw.name,'SOURCE_DIR',d.sources.name,'PLAN_SHA',plan.sha256,flush=True)
snap=campaign.submit_development_proposal(plan,path,out,solver_kind='scipy')
inspect(out,plan)

f=Formal(); f.setUp(); f.fixture(independent=True); check_plan(f.plan)
# Index before binding runtime HEAD; all commits and pushes target the fixture bare origin.
(f.repo/'data/experiment_index.csv').write_text(','.join(INDEX_FIELDS)+'\n')
f.commit('fixture index'); f.publish()
f.prepare(); f.commit('fixture planned'); f.publish()
print('FIXTURE_ROOT',f.repo,'BARE_ORIGIN',f.repo.parent/'origin.git','PLAN_SHA',f.plan.sha256,flush=True)
print('G1',json.dumps(f.verify(),sort_keys=True),flush=True)
snap=campaign.begin_campaign(f.plan,f.ident,**f.kw)
p=f.repo.parent/'proposal-input.yaml'; p.write_text(yaml.safe_dump(ct.CampaignTests.proposal(f,f.definition,snap)))
snap=campaign.submit_campaign_proposal(f.plan,p,f.ident,solver_kind='scipy',**f.kw)
out=f.repo/'results'/f.ident
state,raw=inspect(out,f.plan)
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
summary=preservation.curate_campaign(f.ident,root=f.repo)
print('G3_SUMMARY',json.dumps(summary,sort_keys=True),flush=True)
assert not summary['preservation_errors']
report=preservation.finalize_campaign(f.ident,root=f.repo)
print('G4_FINALIZE',json.dumps(report,sort_keys=True),flush=True)
assert report['stage']=='complete' and report['committed_readback']
f.publish()
decision=preservation.campaign_cleanup_eligibility(f.ident,root=f.repo,resume_needed=False,classification_complete=True)
print('G5_DECISION',json.dumps(decision,sort_keys=True),flush=True)
assert decision['eligible'] and not decision['deleted']
assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
print('DONE: real solver, raw unchanged, no deletion, fixture origin only',flush=True)
