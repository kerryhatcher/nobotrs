#!/usr/bin/env python3
"""Run one local model process at a time, with measured memory and resumable checkpoints.

No unrelated process is signalled. Each child owns a new process group; critical pressure
terminates only that group. Settings remain CPU/float32/full with the recorded deadline.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def memory():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        values[key] = int(value.split()[0]) // 1024
    return values['MemAvailable'], values['SwapFree']


def workload():
    values = {}
    for line in Path('/proc/pressure/memory').read_text().splitlines():
        parts = line.split()
        if parts[0] == 'full':
            values = {k: float(v) for k, v in (p.split('=') for p in parts[1:])}
    return {'memory_full_avg10': values['avg10'], 'memory_full_avg60': values['avg60'],
            'load1': os.getloadavg()[0], 'load_limit': 2 * len(os.sched_getaffinity(0))}


def processes(root):
    # Read only this sweep's process tree. Walking all /proc tasks can itself stall
    # behind unrelated swapped processes precisely when the monitor is needed.
    result = {}
    pending = [root]
    visited = set()
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        path = Path('/proc') / str(pid)
        try:
            values = {}
            for line in (path / 'status').read_text().splitlines():
                if line.startswith(('VmRSS:', 'VmHWM:')):
                    k, v = line.split(':', 1)
                    values[k] = int(v.split()[0])
            result[str(pid)] = {'rss_kib': values.get('VmRSS', 0), 'hwm_kib': values.get('VmHWM', 0)}
            for task in (path / 'task').iterdir():
                try:
                    pending.extend(int(p) for p in (task / 'children').read_text().split())
                except (OSError, ValueError):
                    continue
        except (OSError, ValueError, ProcessLookupError):
            continue
    return result


def atomic(path, value):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--models-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resume-from', type=Path, required=True)
    parser.add_argument('--model', action='append', choices=['desklib', 'conpara', 'detectorscope'])
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--timeout-ms', type=int, default=1200000)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--native-start-mib', type=int, default=8192)
    parser.add_argument('--ds-start-mib', type=int, default=15360)
    parser.add_argument('--wait-for-headroom-seconds', type=int, default=1800)
    args = parser.parse_args()
    stopping = {'signal': None}
    def request_stop(number, _frame):
        stopping['signal'] = number
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(number, request_stop)
    args.out.mkdir(parents=True, exist_ok=True)
    models = args.model or ['desklib', 'conpara', 'detectorscope']
    for model in models:
        out = args.out / model
        out.mkdir(exist_ok=True)
        available, swap = memory()
        required = args.ds_start_mib if model == 'detectorscope' else args.native_start_mib
        monitor = {'model': model, 'model_concurrency': 1, 'start_available_mib': available,
                   'required_start_mib': required, 'start_swap_free_mib': swap,
                   'status': 'starting', 'peak_group_rss_kib': 0, 'process_high_water_kib': {},
                   'minimum_available_mib': available, 'threads': args.threads,
                   'precision': 'float32', 'device': 'cpu', 'timeout_ms': args.timeout_ms}
        attempts = sorted(out.glob('monitor-attempt-*.json'))
        record = out / f'monitor-attempt-{len(attempts)+1}.json'
        wait_started = time.monotonic()
        while True:
            available, swap = memory()
            shared = workload()
            ready = available >= required and shared['memory_full_avg10'] <= 2 and shared['memory_full_avg60'] <= 2 and shared['load1'] <= shared['load_limit']
            monitor['preflight'] = {'available_mib': available, 'swap_free_mib': swap, **shared}
            if ready:
                break
            monitor['status'] = 'waiting_for_stable_headroom'
            monitor['wait_seconds'] = time.monotonic() - wait_started
            atomic(record, monitor)
            if stopping['signal'] is not None or monitor['wait_seconds'] >= args.wait_for_headroom_seconds:
                monitor['status'] = 'deferred_before_launch'
                atomic(record, monitor)
                print(f'DEFER {model}: stable shared headroom unavailable; no model allocated', flush=True)
                return 2
            time.sleep(15)
        env = {k: v for k, v in os.environ.items() if not k.startswith('NOBOTRS_')}
        env.update({'NOBOTRS_MODEL_PYTHON': str(args.python), 'NOBOTRS_MODEL_THREADS': str(args.threads),
                    'RAYON_NUM_THREADS': str(args.threads), 'OMP_NUM_THREADS': str(args.threads),
                    'MKL_NUM_THREADS': str(args.threads), 'OPENBLAS_NUM_THREADS': str(args.threads),
                    'NOBOTRS_DETECTORSCOPE_DEVICE': 'cpu', 'NOBOTRS_DETECTORSCOPE_DTYPE': 'float32'})
        command = [str(args.binary.resolve()), '--model', model, '--models-dir', str(args.models_dir),
                   '--out', str(out), '--resume-from', str(args.resume_from),
                   '--timeout-ms', str(args.timeout_ms), '--minimum-available-mib', '4096']
        monitor['argv'] = command
        started = time.monotonic()
        process = subprocess.Popen(command, env=env, start_new_session=True)
        monitor['root_pid'] = process.pid
        consecutive = 0
        try:
            while process.poll() is None:
                available, swap = memory()
                stats = processes(process.pid)
                monitor['peak_group_rss_kib'] = max(monitor['peak_group_rss_kib'], sum(p['rss_kib'] for p in stats.values()))
                for pid, values in stats.items():
                    monitor['process_high_water_kib'][pid] = max(monitor['process_high_water_kib'].get(pid, 0), values['hwm_kib'])
                monitor['minimum_available_mib'] = min(available, monitor['minimum_available_mib'])
                shared = workload()
                monitor['current_workload'] = shared
                floor = 4096 if swap < 512 else 2048
                monitor['active_available_floor_mib'] = floor
                consecutive = consecutive + 1 if available < floor or shared['memory_full_avg10'] > 10 else 0
                if consecutive >= 3 or stopping['signal'] is not None:
                    monitor['status'] = 'terminated_memory_pressure' if consecutive >= 3 else 'interrupted_by_signal'
                    monitor['stop_signal'] = stopping['signal']
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    break
                monitor['status'] = 'running'
                monitor['elapsed_seconds'] = time.monotonic() - started
                atomic(record, monitor)
                time.sleep(1)
            process.wait()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait()
        monitor['exit_code'] = process.returncode
        monitor['elapsed_seconds'] = time.monotonic() - started
        if monitor['status'] not in ('terminated_memory_pressure', 'interrupted_by_signal'):
            monitor['status'] = 'completed' if process.returncode == 0 else 'incomplete'
        atomic(record, monitor)
        print(f"SWEEP {model}: {monitor['status']}, peak group RSS {monitor['peak_group_rss_kib']/1024:.0f}MiB", flush=True)
        if process.returncode != 0:
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
