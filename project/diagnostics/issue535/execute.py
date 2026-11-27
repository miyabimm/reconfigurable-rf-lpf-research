#!/usr/bin/env python3
"""Run frozen #535 plans sequentially through the standard CLI; stop on abnormal exit."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
INP = Path(__file__).resolve().parent/'inputs'
OUT = Path(sys.argv[1])
PREFLIGHT = Path(sys.argv[2])
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
    assert not OUT.exists()
    pre = json.loads(PREFLIGHT.read_text())
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip() == pre['head']
    assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT,text=True)
    OUT.mkdir()
    for name in ('A','B','C','D'):
        raw = OUT/name
        cmd = [sys.executable, 'scripts/run_rf_search.py','develop','--config',str(INP/f'{name}.yaml'), '--starts',str(INP/'starts.json'), '--search-bounds',str(INP/'bounds.json'), '--output',str(raw), '--spot-checks','{"terminal":[0,111]}','--checkpoint-interval-forwards','1000','--rf-cache-mode','lk']
        start = now()
        with (OUT/f'{name}.log').open('w') as log:
            proc = subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record = {'command':cmd, 'started_utc':start, 'finished_utc':now(), 'exit':proc.returncode}
        (OUT/f'{name}-execution.json').write_text(json.dumps(record,indent=2)+'\n')
        print(name, record, flush=True)
        if proc.returncode not in (0,4):
            print('STOP abnormal exit; no retries or later jobs', flush=True); return 1
        plan = json.loads((raw/'plan.json').read_text()); state = json.loads((raw/'run.json').read_text())
        if plan != pre['plans'][name]['plan'] or state['plan_sha256'] != pre['plans'][name]['plan_sha256'] or state['source_sha256'] != pre['source_sha256'] or state['status'] != 'completed':
            print('STOP frozen plan/source/ledger mismatch; no retries or later jobs',flush=True); return 1
    print('COMPLETE all four plans',flush=True)
    return 0
if __name__ == '__main__': sys.exit(main())
