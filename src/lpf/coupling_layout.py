"""Physical chip row and coupled-inductor admissibility.

Nominal non-strong chip pairs are zero. Signs are electrical dot choices
requiring subsequent physical polarity verification.
"""
import itertools
import numpy as np
from lpf.constraint_versions import load_constraint
def admissible_matrix(types,values,chip_order=None,chip_edges=None,pcb_pairs=None,chip_pcb=None,
                      *,resolved_policy=None):
    policy=load_constraint() if resolved_policy is None else resolved_policy
    limits=policy["coupling_limits"]
    n=len(types)
    if len(values)!=n:raise ValueError('Length mismatch')
    chips=[i for i,t in enumerate(types)
           if t in ('LQP01','LQP02','LQP02HV','LQP02HQ','LQW04')]
    pcbs=[i for i,t in enumerate(types) if t=='PCB_L']
    if len(pcbs)>policy['components']['PCB_L']['max_count_principle']:raise ValueError('PCB count exceeds three')
    if chip_order is None:chip_order=chips
    if sorted(chip_order)!=sorted(chips):raise ValueError('Chip order must be a permutation')
    chip_edges=chip_edges or {}
    pcb_pairs=pcb_pairs or {}
    chip_pcb=chip_pcb or {}
    neighbors={frozenset((a,b)) for a,b in zip(chip_order,chip_order[1:])}
    K=np.eye(n)
    def add(pairs,allowed,limit):
        for pair,k in pairs.items():
            a,b=tuple(pair)
            if a==b or frozenset((a,b)) not in allowed or not np.isfinite(k) or abs(k)>limit+1e-12:
                raise ValueError('Invalid coupling')
            K[a,b]=K[b,a]=float(k)
    add(chip_edges,neighbors,limits['chip_chip_strong_adjacent_abs_k_max'])
    add(pcb_pairs,{frozenset(p) for p in itertools.combinations(pcbs,2)},limits['pcb_pcb_abs_k_max_default'])
    add(chip_pcb,{frozenset((a,b)) for a in chips for b in pcbs},limits['chip_pcb_abs_k_max'])
    L=np.asarray(values,float)
    if np.any(L<=0):raise ValueError('Positive L required')
    validate_coupling_matrix(types,L,K,chip_order=chip_order,resolved_policy=policy)
    return K

def validate_coupling_matrix(types,values,coupling,chip_order=None,
                             chip_strong_max=None,chip_weak_max=None,
                             chip_pcb_max=None,pcb_pcb_max=None,*,nominal=True,resolved_policy=None):
    """Check nominal (default) or explicit weak-coupling sensitivity topology.

    Under RF-F001, nonadjacent chip-chip pairs have nominal k=0; only
    nominal=False enables the separate weak-coupling sensitivity |k|<=0.1.
    This flag never authorizes a nonadjacent *strong* coupling.
    """
    policy=load_constraint() if resolved_policy is None else resolved_policy
    limits=policy["coupling_limits"]
    chip_strong_max=limits["chip_chip_strong_adjacent_abs_k_max"] if chip_strong_max is None else chip_strong_max
    chip_weak_max=limits["chip_chip_nonstrong_abs_k_max"] if chip_weak_max is None else chip_weak_max
    chip_pcb_max=limits["chip_pcb_abs_k_max"] if chip_pcb_max is None else chip_pcb_max
    pcb_pcb_max=limits["pcb_pcb_abs_k_max_default"] if pcb_pcb_max is None else pcb_pcb_max
    n=len(types);L=np.asarray(values,float);K=np.asarray(coupling,float)
    if type(nominal) is not bool:raise ValueError('nominal must be a boolean')
    if (L.shape!=(n,) or np.any(~np.isfinite(L)) or np.any(L<=0)
            or K.shape!=(n,n) or np.any(~np.isfinite(K))
            or not np.allclose(K,K.T,atol=1e-12,rtol=0)
            or not np.allclose(np.diag(K),1,atol=1e-12,rtol=0)):
        raise ValueError('Invalid coupling or inductor values')
    chips=[i for i,t in enumerate(types)
           if t in ('LQP01','LQP02','LQP02HV','LQP02HQ','LQW04')]
    pcbs=[i for i,t in enumerate(types) if t=='PCB_L']
    if len(pcbs)>policy['components']['PCB_L']['max_count_principle']:raise ValueError('PCB count exceeds three')
    pcb_max=policy['components']['PCB_L'].get('max_inductance_nh',
                                             policy['components']['PCB_L']['max_inductance_nh_approx'])
    if any(L[i] > pcb_max*1e-9+1e-21 for i in pcbs):
        raise ValueError('PCB inductance limit exceeded')
    order=chips if chip_order is None else list(chip_order)
    if sorted(order)!=sorted(chips):raise ValueError('Chip order must be a permutation')
    neighbors={frozenset((a,b)) for a,b in zip(order,order[1:])}
    for i in range(n):
        for j in range(i+1,n):
            pair=frozenset((i,j));k=abs(K[i,j])
            if i in chips and j in chips:
                limit=chip_strong_max if pair in neighbors else (0.0 if nominal else chip_weak_max)
            elif (i in chips and j in pcbs) or (j in chips and i in pcbs):
                limit=chip_pcb_max
            elif i in pcbs and j in pcbs:
                limit=pcb_pcb_max
            else:
                limit=0.0
            if k>limit+1e-12:
                raise ValueError('Strong chip coupling requires physical neighbors; pair exceeds its allowed limit')
    M=K*np.sqrt(np.outer(L,L))
    if np.linalg.eigvalsh(M).min()<=0:
        raise ValueError('Inductance matrix not SPD')
    return True
def adjacent_patterns(types,chip_order=None,*,resolved_policy=None):
    chips=[i for i,t in enumerate(types)
           if t in ('LQP01','LQP02','LQP02HV','LQP02HQ','LQW04')]
    order=chips if chip_order is None else chip_order
    if sorted(order)!=sorted(chips):raise ValueError('Invalid order')
    limit=(load_constraint() if resolved_policy is None else resolved_policy)['coupling_limits']['chip_chip_strong_adjacent_abs_k_max']
    pairs=list(zip(order,order[1:]))
    for states in itertools.product((0,-limit,limit),repeat=len(pairs)):
        yield {frozenset(p):v for p,v in zip(pairs,states) if v}
