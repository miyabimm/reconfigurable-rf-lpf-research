#!/usr/bin/env python3
"""Independent, exact power-budget accounting at each candidate's worst passband frequency.

Run from a checked-out repository: python experiments/chatgpt_topology_search/loss_decomposition.py --output-dir results/loss_20261012
No EM, continuous-frequency or global-optimization certification.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import numpy as np

CASES=('B71','B12','B28','B13+B14','B26','B8')
FILES=(
 'candidates/LPF-007.json','candidates/LPF-008.json','candidates/LPF-009.json',
 'experiments/chatgpt_topology_search/runs/EXP-005/A7-03.json',
 'experiments/chatgpt_topology_search/runs/EXP-006/A7-04.json',
 *[f'experiments/chatgpt_topology_search/runs/EXP-008/{x}.json' for x in ('C6-01','C6-02','C6-35')],
 *[f'experiments/chatgpt_topology_search/runs/EXP-009/{x}.json' for x in ('EXP009-L12','EXP009-L15','EXP009-01','EXP009-02')],
 *[f'experiments/chatgpt_topology_search/runs/EXP-010/{x}.json' for x in ('EXP010-01','EXP010-02','EXP010-03','EXP010-04','EXP010-05')],
)


def edge(v):
    out=np.zeros(5)
    a,b=v
    if a:out[int(a)-1]+=1
    if b:out[int(b)-1]-=1
    return out


def normalize(d):
    if 'candidate_id' in d:
        t=d['topology'];cid=d['candidate_id']
        ls=t['inductors'];fs=t['fixed_caps'];vs=t['variable_caps'];pc=[]
        row=d['chip_physical_order'];k=d['neighbor_k_values']
        cvals=d['ic_variable_C_pf_by_setting'];area=d.get('area_units',6 if cid.startswith('LPF-') else 20/3)
    elif 'topology' in d:
        t=d['topology'];cid=d.get('id',d.get('benchmark_id'))
        ls=t['inductors'];fs=t.get('fixed_capacitors',t.get('fixed_caps',[]));vs=t.get('variable_capacitors',t.get('variable_caps',[]));pc=t.get('pcb_pattern_capacitors',[])
        row=t.get('physical_chip_row',d.get('physical_chip_row'))
        k=t.get('signed_adjacent_k',d.get('nominal_adjacent_k'))
        cvals=d['variable_C_pf_by_setting'];area=d.get('chip_area_cost_units',6)
    else:
        cid=d['id'];e=d['inductor_edges'];f=d['fixed_capacitor_edges'];v=d['variable_capacitor_edges']
        ls=[{'id':n,'nodes':es,'L_nH':l,'Q':25} for (n,es),l in zip(sorted(e.items()),d['L_nH'])]
        fs=[{'id':n,'nodes':es,'C_pF':c,'Q':80} for (n,es),c in zip(sorted(f.items()),d['fixed_C_pf'])]
        vs=[{'id':n,'nodes':es,'Q':80} for n,es in sorted(v.items())]
        pc=[];row=('L1','L2','L3','L0');k=d['neighbor_k'];cvals=d['variable_C_pf_by_setting'];area=d['chip_area_cost_units']
    def nodes(z):return list(z.get('nodes',[z.get('a'),z.get('b')]))
    lind=[{'id':x['id'],'nodes':nodes(x),'nH':x['L_nH'],'Q':float(x.get('Q',25))} for x in ls]
    caps=[{'id':x['id'],'nodes':nodes(x),'pF':x['C_pF'],'Q':float(x.get('Q',80)),'type':'PCB_PATTERN_C' if x.get('component_type')=='PCB_PATTERN_C' else 'GJM01'} for x in fs]
    caps += [{'id':x['id'],'nodes':nodes(x),'pF':x['C_pF'],'Q':float(x.get('Q',40)),'type':'PCB_PATTERN_C'} for x in pc]
    settings={c:list(map(float,cvals[c])) for c in CASES}
    varcaps=[{'id':x['id'],'nodes':nodes(x),'Q':float(x.get('Q',80)),'type':'IC_VARIABLE_C'} for x in vs]
    ref=d.get('verified_dense_metrics',d.get('verification',d.get('performance',{})))
    return {'id':cid,'L':lind,'fixed_caps':caps,'var_caps':varcaps,'settings':settings,'row':row,'k':list(k),'area':area,'reference':ref}


def build(c):
    lind=c['L'];L=np.array([z['nH'] for z in lind])*1e-9
    B=np.column_stack([edge(z['nodes']) for z in lind])
    K=np.eye(len(lind));M=np.diag(L).astype(float)
    for j,k in enumerate(c['k']):
        i0=int(c['row'][j][1:]);i1=int(c['row'][j+1][1:]);
        K[i0,i1]=K[i1,i0]=k;M[i0,i1]=M[i1,i0]=k*np.sqrt(L[i0]*L[i1])
    mineig=float(np.linalg.eigvalsh(K).min());assert mineig>0
    Q=np.array([z['Q'] for z in lind]);Zbase=np.diag(L/Q)+1j*M
    YL=B@np.linalg.solve(Zbase,B.T)
    ports=np.zeros((5,5),complex);ports[0,0]=1/50;ports[2,2]=1/(60-40j)
    rhs=np.array([1/50,0,0,0,0],complex)
    return B,L,Zbase,YL,ports,rhs,mineig


def solve(c,bld,case,frequencies_mhz):
    B,L,Zbase,YL,ports,rhs,mineig=bld
    caps=c['fixed_caps'] + [{**x,'pF':cp} for x,cp in zip(c['var_caps'],c['settings'][case])]
    C=np.array([v['pF'] for v in caps])*1e-12
    Q=np.array([v['Q'] for v in caps])
    E=np.array([edge(v['nodes']) for v in caps]);Ycc=(C/(1/Q-1j))
    capcoef=np.einsum('i,ij,ik->jk',Ycc,E,E)
    omega=np.asarray(frequencies_mhz)*2*np.pi*1e6
    if np.ndim(omega)==0:omega=omega.reshape(1)
    A=ports[None,:,:] + YL[None,:,:]/omega[:,None,None] +omega[:,None,None]*capcoef[None,:,:]
    V=np.linalg.solve(A,np.broadcast_to(rhs,(len(omega),5))[...,None])[...,0]
    load=(60/5200)*abs(V[:,2])**2
    il=-10*np.log10(load/.005)
    return il,V,caps,C,Q,E


def at_point(c,bld,setting,mhz):
    B,L,Zbase,YL,ports,rhs,mineig=bld
    omega=2*np.pi*mhz*1e6
    il0,Vred,caps,C,Q,E=solve(c,bld,setting,[mhz])
    capY=np.einsum('i,ij,ik->jk',C/(1/Q-1j),E,E)
    A=np.block([[ports+omega*capY,B],[-B.T,omega*Zbase]])
    v=np.linalg.solve(A,np.r_[rhs,np.zeros(len(L),complex)])
    vn=v[:5];curr=v[5:]
    pL=omega*(L/np.array([z['Q'] for z in c['L']]))*abs(curr)**2
    pC=omega*np.real(C/(1/Q-1j))*abs(E@vn)**2
    p_load=float(abs(vn[2])**2*60/5200)
    p_ref=float(abs(1-2*vn[0])**2/200)
    pav=.005
    loss_L=float(sum(pL));loss_C=float(sum(pC));p_diss=loss_L+loss_C
    resid=pav-p_ref-p_load-p_diss
    mismatch=-10*math.log10((pav-p_ref)/pav)
    diss_db=-10*math.log10(p_load/(pav-p_ref))
    IL=-10*math.log10(p_load/pav)
    contributions=[{'id':z['id'],'type':'LQP02','loss_W':float(x),'pct_source_available':float(x/pav*100), 'loss_dB_allocated':float(x/p_diss*diss_db) if p_diss else 0.0}
                   for z,x in zip(c['L'],pL)]
    contributions +=[{'id':z['id'],'type':z.get('type','GJM01'),'loss_W':float(x),'pct_source_available':float(x/pav*100),'loss_dB_allocated':float(x/p_diss*diss_db) if p_diss else 0.0}
                     for z,x in zip(caps,pC)]
    ret={
      'setting':setting,'frequency_MHz':mhz,'total_IL_dB':IL,'reflection_dB':mismatch,'absorbed_network_dissipation_dB':diss_db,
      'inductor_dissipation_dB_allocated':float(sum(x['loss_dB_allocated'] for x in contributions if x['type']=='LQP02')),
      'GJM01_dissipation_dB_allocated':float(sum(x['loss_dB_allocated'] for x in contributions if x['type']=='GJM01')),
      'IC_variable_C_dissipation_dB_allocated':float(sum(x['loss_dB_allocated'] for x in contributions if x['type']=='IC_VARIABLE_C')),
      'PCB_C_dissipation_dB_allocated':float(sum(x['loss_dB_allocated'] for x in contributions if x['type']=='PCB_PATTERN_C')),
      'P_available_W':pav,'P_reflected_W':p_ref,'P_load_W':p_load,'P_inductor_W':loss_L,'P_capacitor_W':loss_C,
      'P_total_dissipation_W':p_diss,'power_residual_W':float(resid),
      'max_nodal_vs_full_MNA_voltage_difference_V':float(np.max(abs(Vred[0]-vn))),
      'component_losses':contributions,
    }
    assert abs(resid)<1e-12,(c['id'],ret)
    assert abs(ret['total_IL_dB']-il0[0])<1e-9
    assert abs(sum(x['loss_dB_allocated'] for x in contributions)+mismatch-IL)<1e-10
    return ret


def analyze(c,bands,n=7001):
    bld=build(c)
    by_setting=[]
    for case in CASES:
        options=[]
        for b in bands:
            if b['case']!=case or b['region'] not in ('UL','DL'):continue
            fs=np.linspace(float(b['low_mhz']),float(b['high_mhz']),n)
            att,*_=solve(c,bld,case,fs)
            i=int(att.argmax())
            options.append((float(att[i]),float(fs[i]),b['region']))
        max_il,mhz,region=max(options,key=lambda x:x[0]);loss=at_point(c,bld,case,mhz)
        loss['region']=region
        assert abs(loss['total_IL_dB']-max_il)<1e-9
        by_setting.append(loss)
    worst=max(by_setting,key=lambda x:x['total_IL_dB'])
    ref=c['reference'];expected=ref.get('worst_IL_db')
    if expected is not None:
        err=abs(worst['total_IL_dB']-expected)
        assert err<2e-5, f'{c["id"]} value mismatch {worst["total_IL_dB"]} vs {expected} err {err}'
    return {'candidate_id':c['id'],'objective':'full_lpf','component_counts':{
       'LQP02':len(c['L']),'GJM01':sum(1 for z in c['fixed_caps'] if z['type']=='GJM01'),
       'PCB_PATTERN_C':sum(1 for z in c['fixed_caps'] if z['type']=='PCB_PATTERN_C'),
       'IC_VARIABLE_C':len(c['var_caps'])},'chip_area_cost':c['area'],
       'fixed_element_Q':{'L':list(set(x['Q'] for x in c['L'])),'GJM01':80,'IC_variable_C':80,'PCB_pattern_C':40},
       'min_K_eigenvalue':bld[-1],'frequency_grid_per_passband_interval':n,
       'worst_passband':{k:v for k,v in worst.items()},
       'settings_at_their_individual_worst_passband_frequency':by_setting,
       'stored_reference_worst_IL_db':expected,'stored_H2_min_db':ref.get('min_H2_db'), 'stored_H3_min_db':ref.get('min_H3_db'),
       'notes':['The loss allocation is an exact accounting partition, not a causal improvement predicted by removing individual components.',
                'Reflection and internal dissipation dB add exactly, but component dB allocations are proportional shares of internal dissipated power.',
                'Reported values are from 7001-point per passband interval finite-grid local extrema. No EM, nonlinear, process variation or continuous frequency guarantee.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path(__file__).resolve().parents[2]));p.add_argument('--output-dir',required=True)
    p.add_argument('--filter',nargs='*',default=[]);args=p.parse_args()
    root=Path(args.root);out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    bands=list(csv.DictReader((root/'data/bands.csv').open()))
    summary=[]
    for rel in FILES:
        if args.filter and not any(x in rel for x in args.filter):continue
        source=root/rel
        if not source.exists():print('SKIP not found',source);continue
        c=normalize(json.loads(source.read_text()));a=analyze(c,bands)
        a['source_repo_path']=rel
        (out/f"{c['id']}.json").write_text(json.dumps(a,indent=2,ensure_ascii=False)+'\n')
        w=a['worst_passband']
        summary.append({k:a[k] for k in ('candidate_id','chip_area_cost','component_counts','stored_H2_min_db','stored_H3_min_db')}|{k:w[k] for k in ('setting','region','frequency_MHz','total_IL_dB','reflection_dB','absorbed_network_dissipation_dB','inductor_dissipation_dB_allocated','GJM01_dissipation_dB_allocated','IC_variable_C_dissipation_dB_allocated','PCB_C_dissipation_dB_allocated')})
        print(f"{c['id']:12s} {w['setting']:9s} {w['frequency_MHz']:.3f} MHz IL={w['total_IL_dB']:.9f} refl={w['reflection_dB']:.6f} L={w['inductor_dissipation_dB_allocated']:.6f} C={w['absorbed_network_dissipation_dB']-w['inductor_dissipation_dB_allocated']:.6f} residual={w['power_residual_W']:.1e}",flush=True)
    (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()