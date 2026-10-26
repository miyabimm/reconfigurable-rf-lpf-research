"""Reusable legacy finite-search graph primitives.\n\nThe hard-coded 18-thirds area and 3 PCB-L screening limits are historical\nP2/P3/P4 sampling budgets, **not** current RF-F003 or RF-T008 limits.\nKept bit-for-bit equivalent to the original functions in matching_limit.\n"""
from collections import defaultdict
COST={'LQP01':2,'LQP02':3,'LQP02HV':3,'LQP02HQ':3,
      'PCB_L':0,'GJM01':2}
def area_thirds(graph):
    return sum(COST[t] for _,_,t in graph[1])
def has_signal_path(graph):
    n,edges=graph
    adj=[set() for _ in range(n)]
    for a,b,_ in edges:adj[a].add(b);adj[b].add(a)
    seen={1};pending=[1]
    while pending:
        for v in adj[pending.pop()]-seen-{0}:
            seen.add(v);pending.append(v)
    return 2 in seen and all(v in seen for v in range(3,n))
def has_unproductive_internal_leaf(graph):
    n,edges=graph
    degree=[0]*n
    for a,b,_ in edges:degree[a]+=1;degree[b]+=1
    return any(degree[v]<=1 for v in range(3,n))
def topology_signature(graph):
    n,edges=graph
    return (n,tuple(sorted(t for _,_,t in edges)),
            sum(0 in (a,b) for a,b,_ in edges),
            sum(0 not in (a,b) for a,b,_ in edges))
def select_balanced(graphs,per_bin,require_shunt=False):
    """Round-robin topology families in each area bin.

    Returns selected (bin index,graph) pairs and eligible counts. A finite
    selected subset must not be reported as exhaustive topology optimization.
    """
    if per_bin<0:raise ValueError('per_bin must be nonnegative')
    bins=defaultdict(list)
    for graph in graphs:
        n,edges=graph
        if not has_signal_path(graph) or has_unproductive_internal_leaf(graph):continue
        if require_shunt and not any(0 in (a,b) for a,b,_ in edges):continue
        area=area_thirds(graph)
        if area>18 or sum(t=='PCB_L' for _,_,t in edges)>3:continue
        b=0 if area<=6 else 1 if area<=12 else 2
        bins[b].append(graph)
    chosen=[]
    for b in range(3):
        families=defaultdict(list)
        for g in bins[b]:families[topology_signature(g)].append(g)
        for group in families.values():group.sort(key=str)
        keys=sorted(families,key=str)
        picked_in_bin=0
        while picked_in_bin<per_bin and keys:
            for key in list(keys):
                if picked_in_bin>=per_bin:break
                chosen.append((b,families[key].pop(0)))
                picked_in_bin+=1
                if not families[key]:keys.remove(key)
    return chosen,{f'P{b+2}':len(bins[b]) for b in range(3)}

def select_node_balanced(graphs,per_node_bin,require_shunt=False):
    """Each populated (internal-node count, area bin) gets its own budget."""
    if per_node_bin<0:raise ValueError('Negative budget')
    cells=defaultdict(list)
    for g in graphs:
        n,edges=g
        if not has_signal_path(g) or has_unproductive_internal_leaf(g):continue
        if require_shunt and not any(0 in (a,b) for a,b,_ in edges):continue
        area=area_thirds(g)
        if area>18 or sum(t=='PCB_L' for _,_,t in edges)>3:continue
        b=0 if area<=6 else 1 if area<=12 else 2
        cells[(n-3,b)].append(g)
    chosen=[]
    for cell in sorted(cells):
        families=defaultdict(list)
        for g in cells[cell]:families[topology_signature(g)].append(g)
        for group in families.values():group.sort(key=str)
        keys=sorted(families,key=str)
        selected_in_cell=0
        while keys and selected_in_cell<per_node_bin:
            for key in list(keys):
                if selected_in_cell>=per_node_bin:break
                chosen.append((cell,families[key].pop(0)))
                selected_in_cell+=1
                if not families[key]:keys.remove(key)
    return chosen,{f'n{k[0]}_P{k[1]+2}':len(v) for k,v in sorted(cells.items())}
