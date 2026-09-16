"""Order, systematic-name and direction diagnostics for the known stress case."""
import argparse
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
from time import perf_counter

from netlist_comparison import compare, Options
from spice_canonical.canonical_netlist import Connection
from evaluate import stress_fixture
from evaluate_matching import path_baseline, oracle, partition, report_partition


def reordered(data):
    return replace(data,top=replace(data.top,devices=tuple(reversed(data.top.devices))),
                   subcircuits=tuple(replace(c,devices=tuple(reversed(c.devices))) for c in reversed(data.subcircuits)))


def renamed(data):
    def tag(s):return hashlib.sha256(s.encode()).hexdigest()[:16]
    def net(n):return '0' if n=='0' else 'n'+tag(n.casefold())
    def device(n):return n[0]+'x'+tag(n)
    def circuit(n):return 'c'+tag(n)
    def change(c):
        ds=[]
        for d in c.devices:
            call=d.name.lower().startswith('x')
            ds.append(replace(d,name=device(d.name),type=circuit(d.type) if call else d.type,
                              connections=tuple(Connection(net(x.pin) if call else x.pin,net(x.net)) for x in d.connections),
                              parameters=tuple(replace(p,value=circuit(p.value)) if call and p.name=='source_type' else p for p in d.parameters)))
        return replace(c,name=circuit(c.name),pins=tuple(net(p) for p in c.pins),devices=tuple(ds))
    mapping={path:'/'.join([circuit(path.split('/')[0]),*[device(s) for s in path.split('/')[1:]]]) for path in oracle(data,data.top.name)}
    return replace(data,top=change(data.top),subcircuits=tuple(change(c) for c in data.subcircuits)),mapping


def pairs(r):return {(p['a'],p['b']) for p in r['pair_options'] if p['id'] in r['representative_pair_ids']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reports',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    a,b,_=stress_fixture(); ar,ma=renamed(a);br,mb=renamed(b)
    inverse_a,inverse_b={v:k for k,v in ma.items()},{v:k for k,v in mb.items()}
    results={}
    for method,options in [('path_name',None),('v1',Options()),('context',Options(context_mode='frozen_neighbors')),('growth',Options(matching_mode='anchor_growth'))]:
        original=json.loads(gzip.decompress((args.reports/f'stress-{method}.json.gz').read_bytes()))
        expected=pairs(original);checks={}
        for variant,x,y in [('reorder',reordered(a),reordered(b)),('rename',ar,br),('reverse',b,a)]:
            start=perf_counter()
            report=path_baseline(x,y,x.top.name,y.top.name) if options is None else compare(x,y,top_a=x.top.name,top_b=y.top.name,options=options)
            assert report_partition(report,'a')==partition(oracle(x,x.top.name))
            assert report_partition(report,'b')==partition(oracle(y,y.top.name))
            actual=pairs(report)
            if variant=='rename':actual={(inverse_a[p],inverse_b[q]) for p,q in actual}
            if variant=='reverse':actual={(q,p) for p,q in actual}
            checks[variant]={'same_pair_set':actual==expected,'different_pairs':len(actual^expected),'pairs':len(actual),'wall_seconds':perf_counter()-start}
            if variant=='reorder':
                for r in (original,report):
                    r.get('metrics',{}).pop('seconds',None);r.get('relational',{}).pop('seconds',None)
                checks[variant]['same_complete_report_except_timings']=original==json.loads(json.dumps(report))
            print(method,variant,checks[variant],flush=True)
        results[method]=checks
    args.output.write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':main()
