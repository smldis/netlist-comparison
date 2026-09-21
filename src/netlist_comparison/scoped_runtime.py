"""Killable local worker; caller process limits and unrelated matching stay intact."""
from dataclasses import asdict
import json
import multiprocessing
import os
from pathlib import Path
import resource
import tempfile
import time


def _memory(pid):
    try:
        rows = Path(f'/proc/{pid}/status').read_text().splitlines()
        return max(int(row.split()[1]) for row in rows if row.startswith(('VmRSS:', 'VmHWM:')))
    except (OSError, ValueError):
        return 0


def _worker(request, folder):
    # Fork is used only on supported POSIX hosts. Restrict native work to one CPU.
    try:
        if hasattr(os, 'sched_setaffinity'):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        from .operator_scoped import _execute
        result = _execute(request)
        result['operator_scoped']['resources']['worker_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        encoded = json.dumps({'ok': result}, allow_nan=False)
    except (ValueError, TypeError, OSError) as exc:
        encoded = json.dumps({'error': str(exc)})
    except MemoryError:
        encoded = json.dumps({'resource_stop': 'worker_memory_exhaustion'})
    target = Path(folder) / 'result.tmp'
    target.write_text(encoded, encoding='utf-8')
    target.replace(Path(folder) / 'result.json')


def _batch_worker(request, folder):
    try:
        if hasattr(os, 'sched_setaffinity'):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        from .operator_scoped import _execute_batch
        result=_execute_batch(request)
        result['resources']['worker_peak_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        encoded=json.dumps({'ok':result},allow_nan=False)
    except (ValueError,TypeError,OSError) as exc:
        encoded=json.dumps({'error':str(exc)})
    except MemoryError:
        encoded=json.dumps({'resource_stop':'worker_memory_exhaustion'})
    target=Path(folder)/'result.tmp'
    target.write_text(encoded,encoding='utf-8')
    target.replace(Path(folder)/'result.json')


def bounded(request, options):
    from .operator_scoped import incomplete_report
    start = time.monotonic()
    if os.name != 'posix' or not Path('/proc/self/status').exists() or 'fork' not in multiprocessing.get_all_start_methods():
        raise ValueError('operator_scoped currently requires POSIX fork and /proc for its deadline/RSS worker watchdog')
    reason, peak, tree_peak = None, 0, 0
    with tempfile.TemporaryDirectory(prefix='netlist-scoped-') as folder:
        process = multiprocessing.get_context('fork').Process(target=_worker, args=(request, folder))
        process.start()
        try:
            while process.is_alive():
                peak = max(peak, _memory(process.pid))
                tree_peak = max(tree_peak, _memory(os.getpid()) + _memory(process.pid))
                if time.monotonic() - start >= options.operator_time_limit:
                    reason = 'deadline_exhausted'; break
                if peak > options.operator_memory_mib * 1024:
                    reason = 'memory_budget_exhausted'; break
                process.join(.02)
            if reason:
                process.kill(); process.join()
            target = Path(folder) / 'result.json'
            if reason is None and not target.exists():
                reason = 'worker_terminated_before_complete_result'
            if reason is None and target.stat().st_size > 32 * 1024**2:
                reason = 'serialized_result_budget_exhausted'
            if reason is None:
                data = json.loads(target.read_text())
                if 'error' in data:
                    raise ValueError(data['error'])
                reason = data.get('resource_stop')
                if not reason and data['ok']['operator_scoped']['resources'].get('worker_peak_rss_kib',0) > options.operator_memory_mib * 1024:
                    reason = 'memory_budget_exhausted'
            if time.monotonic() - start >= options.operator_time_limit:
                reason = 'deadline_exhausted'
            result = incomplete_report(request, reason) if reason else data['ok']
            result['operator_scoped']['resources'].update(
                observed_parent_worker_rss_upper_kib=tree_peak,
                elapsed_seconds=time.monotonic()-start, configured_seconds=options.operator_time_limit,
                configured_memory_mib=options.operator_memory_mib, observed_peak_rss_kib=max(peak, result['operator_scoped']['resources'].get('worker_peak_rss_kib',0)),
                enforcement='Isolated worker, parent monotonic deadline and /proc RSS watchdog sampled every 20 ms; one CPU. Final stdout/disk I/O is outside computation deadline.',
                incomplete=bool(reason), stop_reason=reason)
            return result
        finally:
            if process.is_alive():
                process.kill(); process.join()


def bounded_batch(request, options):
    """Run one explicit sequential batch in one killable worker."""
    start=time.monotonic()
    if os.name!='posix' or not Path('/proc/self/status').exists() or 'fork' not in multiprocessing.get_all_start_methods():
        raise ValueError('operator_scoped currently requires POSIX fork and /proc for its deadline/RSS worker watchdog')
    # Each proof enforces its own monotonic deadline. The outer allowance also
    # covers one shared preparation interval and serialization.
    configured=options.operator_time_limit*(len(request['windows'])+1)
    result_limit=min(512*1024**2,32*1024**2*len(request['windows']))
    reason,peak,tree_peak=None,0,0
    with tempfile.TemporaryDirectory(prefix='netlist-scoped-batch-') as folder:
        process=multiprocessing.get_context('fork').Process(target=_batch_worker,args=(request,folder))
        process.start()
        try:
            while process.is_alive():
                peak=max(peak,_memory(process.pid));tree_peak=max(tree_peak,_memory(os.getpid())+_memory(process.pid))
                if time.monotonic()-start>=configured:reason='batch_deadline_exhausted';break
                if peak>options.operator_memory_mib*1024:reason='memory_budget_exhausted';break
                process.join(.02)
            if reason:
                process.kill();process.join()
            target=Path(folder)/'result.json'
            if reason is None and not target.exists():reason='worker_terminated_before_complete_result'
            serialized_bytes=target.stat().st_size if reason is None and target.exists() else 0
            if reason is None and serialized_bytes>result_limit:reason='serialized_result_budget_exhausted'
            data=json.loads(target.read_text()) if reason is None else {}
            if 'error' in data:raise ValueError(data['error'])
            reason=reason or data.get('resource_stop')
            if reason:
                return {'schema_version':1,'kind':'operator_scoped_batch_v1','status':reason,'results':[],
                        'resources':{'elapsed_seconds':time.monotonic()-start,'configured_seconds':configured,
                                     'configured_memory_mib':options.operator_memory_mib,'observed_peak_rss_kib':peak,
                                     'observed_parent_worker_rss_upper_kib':tree_peak,'incomplete':True,'stop_reason':reason}}
            result=data['ok'];resources=result['resources']
            if resources.get('worker_peak_rss_kib',0)>options.operator_memory_mib*1024:
                raise ValueError('batch worker exceeded configured memory before final sample')
            resources.update(elapsed_seconds=time.monotonic()-start,configured_seconds=configured,
                             configured_memory_mib=options.operator_memory_mib,
                             observed_peak_rss_kib=max(peak,resources.get('worker_peak_rss_kib',0)),
                             observed_parent_worker_rss_upper_kib=tree_peak,incomplete=False,stop_reason=None,
                             serialized_result_bytes=serialized_bytes,serialized_result_limit_bytes=result_limit,
                             enforcement='One isolated sequential batch worker; parent monotonic deadline and /proc RSS watchdog sampled every 20 ms; one CPU. Each proof also receives the ordinary per-window deadline. Serialized output is limited to 32 MiB per requested window and 512 MiB per batch.')
            return result
        finally:
            if process.is_alive():process.kill();process.join()
