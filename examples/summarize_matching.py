"""Derive retained ranks and stage sizes from saved reports, without rerunning matchers."""
import argparse
import gzip
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('reports',type=Path);args=p.parse_args()
    summary=json.loads((args.reports/'summary.json').read_text());out={}
    for name,case in summary.items():
        out[name]={}
        for method,m in case['methods'].items():
            r=json.loads(gzip.decompress((args.reports/f'{name}-{method}.json.gz').read_bytes()))
            a={x:c['id'] for c in r['a'].get('classes',[]) for x in c['members']}
            b={x:c['id'] for c in r['b'].get('classes',[]) for x in c['members']}
            ranks=[]
            for change in m['changed']:
                edges=[e for e in r.get('candidate_edges',[]) if e['a_class']==a.get(change['a'])]
                truth=next((e for e in edges if e['b_class']==b.get(change['expected_b'])),None)
                ranks.append({'a':change['a'],'historical_class_retained':truth is not None,
                              'historical_cost':truth['cost'] if truth else None,
                              'retained_strictly_better_classes':sum(e['cost']<truth['cost']-1e-9 for e in edges) if truth else None,
                              'retained_equal_cost_classes':sum(abs(e['cost']-truth['cost'])<=1e-9 for e in edges) if truth else None,
                              'scope':'within retained reference class edges; not a full pre-cutoff rank'})
            groups=r.get('groups',[])
            nodes=[len(d.get('a_classes',[]))+len(d.get('b_classes',[]))
                   for g in groups for d in [g.get('assignment_domain',g.get('reference_assignment_domain',{}))]]
            out[name][method]={'changed_candidate_ranks':ranks,'max_reference_singleton_component_nodes':max(nodes,default=0),
                              'class_pair_scores':r.get('metrics',{}).get('class_pair_scores'),
                              'retained_class_edges':len(r.get('candidate_edges',[])),
                              'compressed_report_bytes':(args.reports/f'{name}-{method}.json.gz').stat().st_size}
    (args.reports/'derived.json').write_text(json.dumps(out,indent=2)+'\n')


if __name__=='__main__':main()
