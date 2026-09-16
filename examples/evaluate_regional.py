"""Bounded regional checkpoint: incidence error and two-sided edit coverage."""
import argparse,gzip,json,resource,time
from dataclasses import replace
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.optimize import linear_sum_assignment
from spice_canonical.canonical_netlist import from_text,Device,Connection,Parameter
from netlist_comparison import compare,Options
from evaluate_matching import fixture_cases,oracle,partition,report_partition,HERE
from diagnose_matching import renamed,reordered


def incidence_error(pairs,oa,ob):
    overlap=defaultdict(int);total=0
    for pa,pb in pairs:
        for role in oa[pa]['nets'].keys()&ob[pb]['nets'].keys():
            overlap[oa[pa]['nets'][role],ob[pb]['nets'][role]]+=1;total+=1
    aa={n:i for i,n in enumerate({a for a,b in overlap})};bb={n:i for i,n in enumerate({b for a,b in overlap})}
    matrix=np.zeros((len(aa),len(bb)),dtype=int)
    for (a,b),n in overlap.items():matrix[aa[a],bb[b]]=n
    rr,cc=linear_sum_assignment(matrix,maximize=True)
    return total-int(matrix[rr,cc].sum())


def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    cases=[]
    for name,phase,a,b,ta,tb,ledger,changed,rewired in fixture_cases(None):
        if name in ('stress','stress_body_add_remove','motif_move_body','true_symmetry_values'):
            cases.append((name,a,b,changed,[ledger[x] for x in changed]))
        if name=='stress':
            defs=[]
            for c in b.subcircuits:
                ds=tuple(replace(d,connections=tuple(replace(x,net='n_VSS') if x.pin=='g' else x for x in d.connections)) if c.name=='CELL_v2_SPECIAL' and d.name=='Mz2' else d for d in c.devices)
                defs.append(replace(c,devices=ds))
            top=replace(b.top,devices=tuple(d for d in b.top.devices if d.name!='RzLINK9')+(Device('Cfresh','capacitor',(Connection('p','n_out12'),Connection('n','0')),(Parameter('value','3p'),)),))
            fresh=replace(b,top=top,subcircuits=tuple(defs));ar,ma=renamed(a);br,mb=renamed(fresh)
            cases.append(('fresh_renamed_gate_cut',ar,br,[ma[changed[0]]],[mb[ledger[changed[0]]],mb[ledger[changed[0]]].replace('x'+__import__('hashlib').sha256('Mz1'.encode()).hexdigest()[:16],'x'+__import__('hashlib').sha256('Mz2'.encode()).hexdigest()[:16])]))
        if name=='motif_move_edit':
            text=(HERE/'after.sp').read_text().replace('.model N NMOS','.model N NMOS\n.model P PMOS').replace('M8 OUT IN T VSS N','M8 OUT IN T VSS P').replace('C9 T VSS 1p','C9 T VSS 7p')
            cases.append(('fresh_type_value',a,from_text(text),changed,[ledger[changed[0]],'TOP/XMOVED/XCORE/XNEW/C9']))
    summary={}
    for name,a,b,changed_a,changed_b in cases:
        variants=[('forward',a,b,changed_a,changed_b)]
        if name in ('stress','stress_body_add_remove'):
            ar,ma=renamed(a);br,mb=renamed(b)
            variants += [('renamed',ar,br,[ma[x] for x in changed_a],[mb[x] for x in changed_b]),('reordered',reordered(a),reordered(b),changed_a,changed_b),('reverse',b,a,changed_b,changed_a)]
        for variant,x,y,edita,editb in variants:
            start=time.perf_counter();r=compare(x,y,top_a=x.top.name,top_b=y.top.name,options=Options(matching_mode='regional'));wall=time.perf_counter()-start
            oa,ob=oracle(x,x.top.name),oracle(y,y.top.name)
            assert partition(oa)==report_partition(r,'a');assert partition(ob)==report_partition(r,'b')
            pp={p['id']:p for p in r['pair_options']};hyps=[]
            for h in r['groups'][0]['hypotheses']:
                pairs=[(pp[i]['a'],pp[i]['b']) for i in h]
                hyps.append({'pairs':len(pairs),'incidence_endpoint_disagreements':incidence_error(pairs,oa,ob),
                             'raw_findings':[(pp[i]['a'],pp[i]['b'],pp[i]['raw_differences']) for i in h if pp[i]['raw_differences']],
                             'unpaired_a':sorted(set(oa)-{a for a,b in pairs}),'unpaired_b':sorted(set(ob)-{b for a,b in pairs})})
            edits={}
            for side,objects in [('a',edita),('b',editb)]:
                other='b' if side=='a' else 'a'
                edits[side]=[{'object':o,'counterparts':sorted({p for region in r['inspection_regions'] if o in region[side] for p in region[other]})} for o in objects]
            key=name+'-'+variant
            summary[key]={'hypotheses':hyps,'edits':edits,'seconds':wall,'rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'kernel':r['partial_alignment']}
            (args.output_dir/(key+'.json.gz')).write_bytes(gzip.compress(json.dumps(r).encode(),mtime=0))
            (args.output_dir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            print(key,[(h['pairs'],h['incidence_endpoint_disagreements']) for h in hyps],{s:[len(z['counterparts']) for z in v] for s,v in edits.items()},round(wall,2),flush=True)


if __name__=='__main__':main()
