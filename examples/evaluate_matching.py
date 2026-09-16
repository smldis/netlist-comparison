"""Small reproducible algorithm comparison; evaluator identities never enter matchers.

Not a calibrated benchmark. Saved full reports support independent review.
"""
import argparse
from collections import defaultdict
from dataclasses import asdict, replace
import gzip
import hashlib
import json
from pathlib import Path
import resource
import time

from spice_canonical.canonical_netlist import CanonicalNetlist, Circuit, Device, Connection, Parameter, from_text, from_file
from netlist_comparison import compare, Options, InputScope
from netlist_comparison.expand import expand
from netlist_comparison.report import catalog, connectivity, hierarchy, pair_record
from evaluate import stress_fixture, HERE

BRANCHES = 'R1 a 0 1k\nC1 a x 1p\nR3 x 0 2k\nR2 b 0 2k\nC2 b y 1p\nL1 y 0 1n'


def oracle(data, top):
    """Independent recursive elaboration; never calls comparator expansion.

    Only for these complete fixture calls: formal pin bindings, ground global,
    no other globals. Net keys are tuples, deliberately unlike runtime strings.
    """
    definitions = {c.name.casefold(): c for c in [data.top, *data.subcircuits]}
    objects = {}
    def walk(circuit, path, bindings):
        for d in circuit.devices:
            nets = {c.pin.casefold(): ('ground',) if c.net == '0' else
                    bindings.get(c.net.casefold(), (*path, ':', c.net.casefold())) for c in d.connections}
            target = definitions.get(dict((p.name.casefold(), p.value) for p in d.parameters).get('source_type', d.type).casefold())
            if d.name.lower().startswith('x') and target:
                walk(target, (*path, d.name), nets)
            else:
                objects['/'.join((*path, d.name))] = {'device': d, 'nets': nets}
    root = definitions[top.casefold()]
    walk(root, (root.name,), {})
    return objects


def partition(objects):
    nets = defaultdict(set)
    for path, row in objects.items():
        for role, net in row['nets'].items():
            nets[net].add((path, role.casefold()))
    return {frozenset(tokens) for tokens in nets.values()}


def report_partition(report, side):
    return partition({row['id']: {'nets': row['resolved_nets']} for row in report[side]['objects']})


def path_baseline(a, b, ta, tb):
    va, vb = expand(a, ta, InputScope(), Options()), expand(b, tb, InputScope(), Options())
    # Strong simple baseline: equal full paths, then globally unique leaf names.
    right = {l.path.casefold(): l for l in vb.leaves}
    pairs, used_a, used_b = [], set(), set()
    for l in va.leaves:
        r = right.get(l.path.casefold())
        if r and not l.opaque and not r.opaque:
            pairs.append((l, r)); used_a.add(l.path); used_b.add(r.path)
    names_a, names_b = defaultdict(list), defaultdict(list)
    for side, used, names in ((va, used_a, names_a), (vb, used_b, names_b)):
        for l in side.leaves:
            if l.path not in used and not l.opaque:
                names[l.device.name.casefold()].append(l)
    for name in sorted(names_a.keys() & names_b.keys()):
        if len(names_a[name]) == len(names_b[name]) == 1:
            pairs.append((names_a[name][0], names_b[name][0]))
    records = [pair_record(l, r, f'p{i}', 'baseline', 0) for i, (l, r) in enumerate(pairs)]
    return {'algorithm': 'exact_path_then_unique_leaf_name', 'a': catalog(va), 'b': catalog(vb),
            'pair_options': records, 'representative_pair_ids': [r['id'] for r in records],
            'connectivity': connectivity(va, vb, records), 'hierarchy': hierarchy(va, vb, records)}


def regroup(data, changes=None, remove=(), add=()):
    """Group a flat fixture across two populated containers; rename every leaf."""
    changes = changes or {}
    defs, calls, ledger = [], [], {}
    original = list(data.top.devices)
    for group in range(2):
        devices = [changes.get(d.name, d) for i, d in enumerate(original) if i % 2 == group and d.name not in remove]
        if group == 1:
            devices += list(add)
        pins = sorted({c.net for d in devices for c in d.connections if c.net != '0'})
        rewritten = tuple(replace(d, name=d.name[0]+'q'+d.name[1:]) for d in devices)
        defs.append(Circuit(f'PART{group}', tuple(pins), rewritten))
        calls.append(Device(f'XP{group}', f'PART{group}', tuple(Connection(p, p) for p in pins)))
        for d in devices:
            if d.name in {x.name for x in original}:
                ledger['TOP/'+d.name] = f'NEW/XWRAP/XP{group}/'+d.name[0]+'q'+d.name[1:]
    wrap = Circuit('WRAP', tuple(sorted({c.net for d in calls for c in d.connections})), tuple(calls))
    top = Circuit('NEW', (), (Device('XWRAP', 'WRAP', tuple(Connection(p, p) for p in wrap.pins)),))
    return CanonicalNetlist(top, (*defs, wrap)), ledger


def fixture_cases(public):
    a = from_text(BRANCHES)
    changes = {d.name: replace(d, parameters=(Parameter('value', '2k' if d.name == 'R1' else '1k'),))
               for d in a.top.devices if d.name in ('R1', 'R2')}
    b, ledger = regroup(a, changes)
    yield 'branches_regroup_values', 'development', a, b, 'TOP', 'NEW', ledger, ['TOP/R1', 'TOP/R2'], set()
    a = from_file(HERE/'before.sp'); b = from_file(HERE/'after.sp')
    ledger = dict(zip(['TOP/XOLD/XCH/'+n for n in ('M1','M2','R1','C1')],
                      ['TOP/XMOVED/XCORE/XNEW/'+n for n in ('M8','M9','R9','C9')]))
    yield 'motif_move_edit', 'development', a,b,'TOP','TOP',ledger,['TOP/XOLD/XCH/M1'],set()
    a,b,ledger=stress_fixture()
    yield 'stress', 'known_challenge',a,b,'TOP','TOP_v2',ledger,['TOP/XB0/XL/XL/XL/M1'],set()
    # Untouched combination: same specialization/wrap, body rewire, bridge removal,
    # a new capacitor. Mutation ledger remains outside canonical objects.
    defs=[]
    for c in b.subcircuits:
        ds=tuple(replace(d,connections=tuple(replace(x,net='n_IN') if x.pin=='b' else x for x in d.connections))
                 if c.name=='CELL_v2_SPECIAL' and d.name=='Mz1' else d for d in c.devices)
        defs.append(replace(c,devices=ds))
    top=replace(b.top,devices=tuple(d for d in b.top.devices if d.name!='RzLINK20')+
                (Device('Cadded','capacitor',(Connection('p','n_out3'),Connection('n','0')),(Parameter('value','9p'),)),))
    ledger2={k:v for k,v in ledger.items() if k!='TOP/RLINK20'}
    yield 'stress_body_add_remove', 'held_out',a,replace(b,top=top,subcircuits=tuple(defs)),'TOP','TOP_v2',ledger2,['TOP/XB0/XL/XL/XL/M1'],{('TOP/XB0/XL/XL/XL/M1','b')}
    # Combine the small moved edit with a body-net edit.
    a=from_file(HERE/'before.sp'); b=from_text((HERE/'after.sp').read_text().replace('M8 OUT IN T VSS','M8 OUT IN T IN'))
    ledger=dict(zip(['TOP/XOLD/XCH/'+n for n in ('M1','M2','R1','C1')],['TOP/XMOVED/XCORE/XNEW/'+n for n in ('M8','M9','R9','C9')]))
    yield 'motif_move_body', 'held_out',a,b,'TOP','TOP',ledger,['TOP/XOLD/XCH/M1'],{('TOP/XOLD/XCH/M1','b')}
    a=from_text(BRANCHES)
    b,ledger=regroup(a,remove=('L1',),add=(Device('Mnew','nmos',(Connection('d','y'),Connection('g','a'),Connection('s','0'),Connection('b','0'))),))
    yield 'branches_regroup_add_remove', 'held_out',a,b,'TOP','NEW',ledger,['TOP/C2'],set()
    a=from_text('R1 a 0 1k\nR2 a 0 2k\nC1 a 0 1p')
    b,ledger=regroup(a,{d.name:replace(d,parameters=(Parameter('value','9k'),)) for d in a.top.devices if d.name.startswith('R')})
    yield 'true_symmetry_values', 'held_out',a,b,'TOP','NEW',ledger,['TOP/R1'],set()
    # Shared vs specialized unevaluated defaults and explicit override.
    text='.model N NMOS\n.subckt CELL IN OUT VSS W=2u\nM1 OUT IN T VSS N W=W L=1u\nM2 T IN VSS VSS N W=3u L=1u\nR1 OUT VSS 1k\nC1 T VSS 1p\n.ends\nX1 in out 0 CELL W=4u\nX2 out end 0 CELL\nL1 end 0 1n'
    a=from_text(text)
    shared=replace(a.subcircuits[0],parameter_defaults=(Parameter('W','5u'),))
    specialized=replace(shared,name='SPECIAL',parameter_defaults=(Parameter('W','7u'),))
    top=replace(a.top,devices=tuple(replace(d,type='SPECIAL',parameters=(Parameter('W','8u'),)) if d.name=='X1' else d for d in a.top.devices))
    b=replace(a,top=top,subcircuits=(shared,specialized))
    ledger={p:p for p in oracle(a,'TOP')}
    yield 'shared_specialized_defaults', 'held_out',a,b,'TOP','TOP',ledger,['TOP/X1/M1','TOP/X2/M1'],set()
    if public:
        a=from_file(public,spice_format='ngspice')
        owner=next(c for c in [a.top,*a.subcircuits] if any(d.name=='R112' for d in c.devices))
        updated=replace(owner,devices=tuple(replace(d,parameters=(replace(d.parameters[0],value='{2*('+d.parameters[0].value+')}'),*d.parameters[1:])) if d.name=='R112' else d for d in owner.devices))
        b=replace(a,top=updated if owner is a.top else a.top,subcircuits=tuple(updated if c is owner else c for c in a.subcircuits))
        ledger={p:p for p in oracle(a,a.top.name)}
        yield 'tia_names_unchanged','known_challenge',a,b,a.top.name,b.top.name,ledger,['TOP/R112'],set()


def metrics(r, ledger, changed, oa, ob):
    pairs={p['id']:p for p in r['pair_options']}
    selected=[pairs[i] for i in r['representative_pair_ids']]
    # Proven terminal twins are interchangeable. No arbitrary ledger identity
    # is asserted for these. More general automorphisms are not certified here.
    twins=defaultdict(list)
    for p,row in oa.items():
        twins[(row['device'].type.casefold(),tuple(sorted(row['nets'].items())))].append(p)
    admissible={p:{ledger[q] for q in members if q in ledger} for members in twins.values() for p in members}
    wrong=[(p['a'],p['b']) for p in selected if p['b'] not in admissible.get(p['a'],set())]
    diffs=[p for p in selected if p['raw_differences']]
    false_diffs=[p['id'] for p in diffs if p['b'] not in admissible.get(p['a'],set())]
    ca={m:c['id'] for c in r['a'].get('classes',[]) for m in c['members']}
    cb={m:c['id'] for c in r['b'].get('classes',[]) for m in c['members']}
    edges={(e['a_class'],e['b_class']) for e in r.get('candidate_edges',[]) if e['eligible']}
    lookup={c['id']:c['members'] for c in r['b'].get('classes',[])}
    changes=[]
    for p in changed:
        proposals={q['b'] for q in selected if q['a']==p}
        regions=[s for s in r.get('inspection_regions',[]) if p in s['a']]
        ref={m for ac,bc in edges if ac==ca.get(p) for m in lookup[bc]}
        suggested=proposals or {m for s in regions for m in s['b']} or ref
        groups=[g for g in r.get('groups',[]) if ca.get(p) in g['a_classes']]
        changes.append({'a':p,'expected_b':ledger.get(p),'paired':bool(proposals),
                        'suggested_size_b':len(suggested),'suggested_contains_history':ledger.get(p) in suggested,
                        'reference_eligible_size_b':len(ref),
                        'competition_size_b':max((len({m for c in g['b_classes'] for m in lookup[c]}) for g in groups),default=0),
                        'raw_finding':any(q['a']==p and q['raw_differences'] for q in selected)})
    return {'leaves':{s:len(r[s]['objects']) for s in ('a','b')},'depth':{s:r[s]['max_depth'] for s in ('a','b')},
            'proposals':len(selected),'ledger_or_proven_twin_agreement':len(selected)-len(wrong),
            'ledger_disagreements':wrong,'disagreement_scope':'Historical mapping modulo exact terminal twins; other automorphisms not certified',
            'raw_findings':len(diffs),'false_raw_findings_from_disagreements':false_diffs,
            'unpaired_a':len(oa)-len(selected),'changed':changes,
            'eligible_reference_history_retention':sum((ca.get(a),cb.get(b)) in edges for a,b in ledger.items()) if ca else None,
            'class_counts':{s:len(r[s].get('classes',[])) for s in ('a','b')},'metrics':r.get('metrics',{}),
            'growth':{k:v for k,v in r.get('relational',{}).items() if k in ('seed_count','rounds','stop','candidate_work','seconds')},
            'partition_split_rows':sum(x['a_partitioned_across_b'] or x['b_collects_multiple_a'] for x in r['connectivity']['overlap']),
            'definition_changes':[x for x in r['hierarchy']['definition_options'] if x['raw_differences']]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--public-netlist',type=Path)
    parser.add_argument('--phase',choices=('development','all'),default='all')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    summaries={}
    for name,phase,a,b,ta,tb,ledger,changed,rewired in fixture_cases(args.public_netlist):
        if args.phase=='development' and phase=='held_out':continue
        oa,ob=oracle(a,ta),oracle(b,tb)
        assert set(ledger)<=oa.keys() and set(ledger.values())<=ob.keys()
        # Verify the complete transformed incidence partition outside explicitly
        # rewired terminals and added/removed objects, independently of matcher.
        pa={p:{'nets':{role:net for role,net in row['nets'].items() if (p,role) not in rewired}}
            for p,row in oa.items() if p in ledger}
        pb={p:{'nets':{role:net for role,net in ob[q]['nets'].items() if (p,role) not in rewired}}
            for p,q in ledger.items()}
        assert partition(pa)==partition(pb),name
        cases={'phase':phase,'independent_incidence_checked':True,'ledger_pairs':len(ledger),'methods':{}}
        for method,options in [('path_name',None),('v1',Options()),('context',Options(context_mode='frozen_neighbors')),('growth',Options(matching_mode='anchor_growth'))]:
            start=time.perf_counter()
            r=path_baseline(a,b,ta,tb) if options is None else compare(a,b,top_a=ta,top_b=tb,options=options)
            wall=time.perf_counter()-start
            assert report_partition(r,'a')==partition(oa),(name,method,'a')
            assert report_partition(r,'b')==partition(ob),(name,method,'b')
            result=metrics(r,ledger,changed,oa,ob);result['wall_seconds']=wall
            result['peak_process_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            raw=json.dumps(r,sort_keys=True,allow_nan=False).encode()
            (args.output_dir/f'{name}-{method}.json.gz').write_bytes(gzip.compress(raw,mtime=0))
            result['report_bytes']=len(raw);cases['methods'][method]=result
            print(name,method,'pairs',result['proposals'],'disagreements',len(result['ledger_disagreements']),
                  'regions',[(x['suggested_size_b'],x['suggested_contains_history']) for x in result['changed']],f'{wall:.3f}s',flush=True)
        summaries[name]=cases
        (args.output_dir/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    if args.public_netlist:
        (args.output_dir/'public-source.json').write_text(json.dumps({'path':str(args.public_netlist),'sha256':hashlib.sha256(args.public_netlist.read_bytes()).hexdigest()})+'\n')


if __name__=='__main__':main()
