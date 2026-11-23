#!/usr/bin/env python3
"""Compare exact committed squared_terms functions, alternating order, unweighted."""
import importlib.util, json, os, pathlib, statistics, sys, time
import numpy as np
roots = [pathlib.Path(p) for p in sys.argv[1:3]]
funcs = []
for root in roots:
    spec = importlib.util.spec_from_file_location('objective_bench_'+str(len(funcs)),root/'src/lpf/optimizers/_objectives.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); funcs.append(module.squared_terms)
cpu = sorted(os.sched_getaffinity(0))[-1]; os.sched_setaffinity(0,{cpu})
rng = np.random.default_rng(496); cases = {str(n): rng.normal(size=n) for n in (8,70,1024)}
iterations=30000; rows=[]
for name, r in cases.items():
    for func in funcs:
        for _ in range(1000): func(r,None)
    for i in range(7):
        for arm in ((0,1) if i%2==0 else (1,0)):
            t=time.perf_counter_ns()
            for _ in range(iterations): funcs[arm](r,None)
            rows.append(dict(length=int(name),round=i+1,arm='AB'[arm],ns_per_call=(time.perf_counter_ns()-t)/iterations))
summary={}
for name in cases:
    vals={arm:[r['ns_per_call'] for r in rows if r['length']==int(name) and r['arm']==arm] for arm in 'AB'}
    summary[name]={arm:{'median_ns':statistics.median(v),'min_ns':min(v),'max_ns':max(v)} for arm,v in vals.items()}
print(json.dumps(dict(cpu=cpu,iterations=iterations,seed=496,rows=rows,summary=summary,loadavg=os.getloadavg()),indent=2))
