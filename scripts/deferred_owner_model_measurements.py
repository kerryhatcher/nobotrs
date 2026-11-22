#!/usr/bin/env python3
"""Cold, bounded scheduler for the owner's local model measurements and numeric reports.

The scheduler allocates no model while waiting. A pressure abort returns to a sustained
quiet window before any missing score is attempted again; recovery rounds are bounded.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
from run_owner_model_sweeps import atomic, memory, workload


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--models-dir',type=Path,required=True)
    p.add_argument('--python',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--max-wait-seconds',type=int,default=1800)
    p.add_argument('--quiet-seconds',type=int,default=300)
    p.add_argument('--max-pressure-recoveries',type=int,default=3)
    args=p.parse_args()
    stopping={'signal':None}
    def stop(number,_frame):stopping['signal']=number
    for number in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(number,stop)
    record=args.root/f"deferred-scheduler-attempt-{len(list(args.root.glob('deferred-scheduler-attempt-*.json')))+1}.json"
    state={'schema_version':'deferred-owner-model-scheduler-v1','argv':sys.argv,'status':'waiting','model_allocated_while_waiting':False,'max_wait_seconds':args.max_wait_seconds,'quiet_seconds':args.quiet_seconds,'max_pressure_recoveries':args.max_pressure_recoveries,'models':{}}
    recovery=args.root/'recovery'
    for model in ('desklib','conpara','detectorscope'):
        for round_number in range(args.max_pressure_recoveries+1):
            wait_start=time.monotonic();quiet_since=None
            required=15360 if model=='detectorscope' else 8192
            while True:
                available,swap=memory();shared=workload()
                pressure=Path('/proc/pressure/memory').read_text()
                full=next(line for line in pressure.splitlines() if line.startswith('full '))
                avg300=float(dict(item.split('=') for item in full.split()[1:])['avg300'])
                ready=available>=required and shared['memory_full_avg10']<=1 and shared['memory_full_avg60']<=1 and avg300<=2 and shared['load1']<=shared['load_limit']
                now=time.monotonic();quiet_since=(quiet_since or now) if ready else None
                state.update(status='waiting_for_sustained_headroom',active_model=model,recovery_round=round_number,available_mib=available,required_start_mib=required,swap_free_mib=swap,memory_full_avg300=avg300,workload=shared,wait_seconds=now-wait_start,quiet_elapsed_seconds=now-quiet_since if quiet_since else 0)
                atomic(record,state)
                if stopping['signal'] is not None or now-wait_start>=args.max_wait_seconds:
                    state['status']='deferred_headroom_unavailable' if stopping['signal'] is None else 'interrupted_by_request';atomic(record,state)
                    return 2
                if ready and now-quiet_since>=args.quiet_seconds:break
                time.sleep(15)
            command=[str(args.python),'scripts/run_owner_model_sweeps.py','--binary',str(args.binary),'--models-dir',str(args.models_dir),'--out',str(recovery),'--resume-from',str(args.root),'--python',str(args.python),'--model',model,'--wait-for-headroom-seconds','60']
            state['status']='measuring';state['model_allocated_while_waiting']=False;atomic(record,state)
            process=subprocess.Popen(command)
            while process.poll() is None:
                if stopping['signal'] is not None:process.send_signal(signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            monitors=list((recovery/model).glob('monitor-attempt-*.json'))
            monitor=json.loads(max(monitors,key=lambda path:int(path.stem.rsplit('-',1)[1])).read_text()) if monitors else {}
            state['models'][model]={'exit_code':process.returncode,'monitor_status':monitor.get('status'),'round':round_number}
            atomic(record,state)
            if stopping['signal'] is not None:
                state['status']='interrupted_by_request';atomic(record,state);return 2
            if process.returncode==0:break
            run_path=recovery/model/'run.json';run=json.loads(run_path.read_text()) if run_path.is_file() else {}
            pressure_abort=monitor.get('status') in ('terminated_memory_pressure','deferred_before_launch') or bool(run.get('deferred'))
            if not pressure_abort or round_number==args.max_pressure_recoveries:
                state['status']='blocked_or_recovery_budget_exhausted';atomic(record,state);return 2
        else:
            return 2
    state['status']='postprocessing';atomic(record,state)
    consolidated=args.root/'consolidated'
    commands=[
        [str(args.python),'scripts/consolidate_owner_model_sweeps.py','--original',str(args.root),'--recovery',str(recovery),'--out',str(consolidated)],
        [str(args.python),'scripts/summarize_owner_models.py',str(consolidated),'--out',str(consolidated/'coverage-summary.json')],
        [str(args.python),'scripts/hotspot_validity.py','--owner-baseline',str(consolidated),'--out','evaluation/reports/owner-model-diagnostics.json'],
        [str(args.python),'scripts/survey_detectorscope_features.py','--binary','target/release/nobotrs','--corpus','owner-posts-v1','--models-dir',str(args.models_dir),'--reports-dir',str(consolidated),'--out','evaluation/reports/detectorscope-feature-survey.csv'],
    ]
    state['postprocessing']=[]
    for command in commands:
        result=subprocess.run(command,check=False)
        state['postprocessing'].append({'argv':command,'exit_code':result.returncode});atomic(record,state)
        # A coverage summary can honestly return2 when measured outcomes include failures.
        if result.returncode!=0 and 'scripts/summarize_owner_models.py' not in command:
            state['status']='postprocessing_incomplete';atomic(record,state);return 2
    state['status']='measurements_finished_review_required';atomic(record,state)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
