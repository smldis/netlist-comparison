"""Experimental revisable partial QAP alignment.

Paper lineage: FAQ/FUGAL's feature-regularized adjacency objective and
Frank-Wolfe relaxation. Independently implemented, with terminal-relation
channels, substochastic partial maps, exact optional LAP, and bounded restarts.
Not a reproduction of FUGAL's Sinkhorn/continuation algorithm or performance.
"""
from collections import defaultdict
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.sparse import csr_matrix
from scipy.spatial.distance import cdist

from .candidates import features
from .relational import structural_labels


def vectors(view):
    classes=features(view)
    result=np.empty((len(view.leaves),len(classes[0].vector))) if classes else np.empty((0,216))
    for c in classes:
        result[c.members]=c.vector
    return result


def channels(view):
    edges=defaultdict(dict)
    for endpoints in view.nets.values():
        degree=len({i for i,_ in endpoints})
        if degree>32 or degree<2:continue
        for i,r in endpoints:
            for j,s in endpoints:
                if i!=j:
                    key=(r.casefold(),s.casefold())
                    edges[key][i,j]=edges[key].get((i,j),0)+1/max(1,len(endpoints)-1)
    n=len(view.leaves)
    return {r:csr_matrix((list(es.values()),([i for i,j in es],[j for i,j in es])),shape=(n,n)) for r,es in edges.items()}


def name_vectors(view):
    # Inspectable weak name evidence, including container labels. No values.
    rows=[]
    for leaf in view.leaves:
        grams=set()
        for part in leaf.segments[1:]:
            word='^'+part.casefold()+'$'
            grams.update(word[i:i+2] for i in range(len(word)-1))
        rows.append(grams)
    return rows


def name_similarity(a,b):
    rows=name_vectors(a);cols=name_vectors(b)
    vocab={g:i for i,g in enumerate(sorted(set().union(*rows,*cols)))}
    def matrix(values):
        ii=[];jj=[];data=[]
        for i,gs in enumerate(values):
            for g in gs:ii.append(i);jj.append(vocab[g]);data.append(1/np.sqrt(max(1,len(gs))))
        return csr_matrix((data,(ii,jj)),shape=(len(values),len(vocab)))
    return (matrix(rows)@matrix(cols).T).toarray()


def match_partial(a,b,*,iterations=6,max_cells=5000000,use_names=True):
    start=perf_counter();na,nb=len(a.leaves),len(b.leaves)
    if na*nb>max_cells or not na or not nb:
        return [],{'stop':'size_budget' if na*nb>max_cells else 'empty','seconds':perf_counter()-start,'hypotheses':[]}
    unary=cdist(vectors(a),vectors(b),'cityblock')/8
    ta=np.array([x.device.type.casefold() for x in a.leaves]);tb=np.array([x.device.type.casefold() for x in b.leaves])
    unary+=.12*(ta[:,None]!=tb[None,:])
    ha,_=structural_labels(a,3,32);hb,_=structural_labels(b,3,32)
    for depth in (1,2,3):
        unary+=.04*(np.array(ha[depth])[:,None]!=np.array(hb[depth])[None,:])
    # Opaque objects are never optimization variables for correspondence.
    opa=np.array([bool(x.opaque) for x in a.leaves]);opb=np.array([bool(x.opaque) for x in b.leaves])
    from .blackbox import key as black_box_key
    forbidden=opa[:,None]|opb[None,:]
    forbidden |= (np.array([black_box_key(x) for x in a.leaves])[:,None] !=
                  np.array([black_box_key(x) for x in b.leaves])[None,:])
    aa,bb=channels(a),channels(b)
    common=sorted(aa.keys()&bb.keys())
    def relation(p):
        out=np.zeros_like(p)
        sparse=np.count_nonzero(p)<max(1,p.size//100)
        source=csr_matrix(p) if sparse else p
        for role in common:
            if sparse:
                out+=(aa[role]@source@bb[role].T).toarray()
            else:
                out+=bb[role].dot(aa[role].dot(source).T).T
        return out
    def lap(cost):
        matrix=np.full((na,nb+na),1e6)
        matrix[:,:nb]=cost
        matrix[np.arange(na),nb+np.arange(na)]=0
        rows,cols=linear_sum_assignment(matrix)
        q=np.zeros((na,nb))
        real=cols<nb
        q[rows[real],cols[real]]=1
        return q
    plans=[];traces=[]
    names=name_similarity(a,b) if use_names else np.zeros_like(unary)
    # Both hypotheses are revisable; names cannot silently suppress the
    # independent structure-only solution.
    starts=[('structure',0.),('weak_names',.12)] if use_names else [('structure',0.)]
    for label,name_weight in starts:
        cost=unary-name_weight*names-.6
        cost[forbidden]=1e6
        # Optional unary assignment is a starting vertex, never fixed seeds.
        p=lap(cost)
        trace=[]
        for step in range(iterations):
            rp=relation(p)
            grad=cost-.35*rp
            q=lap(grad)
            d=q-p;rd=relation(d)
            linear=float(np.sum(cost*d)-.35*np.sum(rp*d))
            quadratic=-.175*float(np.sum(d*rd))
            choices=[0.,1.]
            if quadratic>1e-12:choices.append(float(np.clip(-linear/(2*quadratic),0,1)))
            alpha=min(choices,key=lambda x:linear*x+quadratic*x*x)
            p+=alpha*d
            trace.append({'iteration':step,'step':alpha,'objective':float(np.sum(cost*p)-.175*np.sum(p*relation(p)))})
            if alpha<1e-8:break
        rounded=lap(cost-.35*relation(p))
        edges=list(zip(*np.where(rounded>.5)))
        plans.append([(int(i),int(j)) for i,j in edges])
        traces.append({'basis':label,'name_weight':name_weight,'trace':trace,'pairs':len(edges)})
    return plans,{'stop':'bounded_optimization','method':'partial_role_qap_v2','iterations_limit':iterations,
                  'names_used':use_names,'dense_cells':na*nb,'relation_channels':len(common),'hypotheses':traces,'seconds':perf_counter()-start,
                  'weights':{'type':.12,'wl_mismatch_per_depth':.04,'relation':.35,'unmatched_per_side':.3,'weak_names':.12},
                  'limitation':'Local nonconvex optimization; ensemble alternatives are not exhaustive. No correspondence is fixed as a seed.'}


def apply_partial_report(result,a,b,options):
    """Expose complete competing assignments; never hide disagreement in one hint."""
    from dataclasses import asdict
    from .report import pair_record,connectivity,hierarchy
    if options.matching_mode == "regional":
        from .regional import match_regional
        plans,evidence=match_regional(a,b,work_limit=options.regional_work_limit,
                                      omission_work_limit=options.omission_work_limit,
                                      swap_work_limit=options.swap_work_limit)
    else:
        plans,evidence=match_partial(a,b,max_cells=min(5000000,options.max_pair_scores))
    representative_selection = None
    if options.matching_mode == 'regional':
        from .twins import representatives
        plans, representative_selection = representatives(a, b, plans)
        if options.component_presentation == 'minimum_raw':
            from .component_presentation import refine
            plans, component_selection = refine(a, b, plans, evidence.get('component_permutation_factors', []))
            representative_selection['components'] = component_selection
    # Use a separate presentation group. Retain reference retrieval/groups as
    # alternatives, with their original fixed-feature proposals kept separately.
    result['reference_proposals']={k:result[k] for k in ('groups','pair_options','representative_pair_ids')}
    edges=sorted({edge for plan in plans for edge in plan})
    ids={edge:f'q{i}' for i,edge in enumerate(edges)}
    records=[]
    plan_sets = [set(plan) for plan in plans]
    membership = defaultdict(list)
    for k, plan in enumerate(plan_sets):
        for edge in plan:
            membership[edge].append(k)
    for i,j in edges:
        p=pair_record(a.leaves[i],b.leaves[j],ids[i,j],'qap',None)
        p.update(status='representative' if plan_sets and (i,j) in plan_sets[-1] else 'alternative',correspondence='tentative',
                 evidence={'basis':evidence.get('method','revisable_partial_role_qap'),'hypotheses':membership[i,j]})
        records.append(p)
    # Exact terminal twins need explicit alternatives even when the LAP tie
    # resolver returns the same arbitrary permutation in every restart.
    from .twins import terminal_twins
    twin_a = {i: group for group in terminal_twins(a) for i in group}
    twin_b = {i: group for group in terminal_twins(b) for i in group}
    options_by_a=defaultdict(set)
    for i,j in edges:
        for aa in twin_a.get(i,[i]):options_by_a[aa].update(twin_b.get(j,[j]))
    grouped=defaultdict(list)
    for i,js in options_by_a.items():grouped[tuple(sorted(js))].append(i)
    regions=[{'a':[a.leaves[i].path for i in ii],'b':[b.leaves[j].path for j in js],
              'basis':'union_of_coupled_alignment_hypotheses_and_exact_terminal_twins',
              'constraint':'one_to_one_leaf_pairs','alternatives_complete':False}
             for js,ii in sorted(grouped.items())]
    factors = evidence.get('component_permutation_factors', [])
    if factors:
        from .budgeted import factor_regions
        regions = factor_regions(a, b, plans, factors)
    selected=[p for p in records if p['status']=='representative']
    result.update(algorithm=evidence.get('method','partial_role_qap_v2'),options=asdict(options),pair_options=records,
                  representative_pair_ids=[p['id'] for p in selected],
                  groups=[{'id':'qap','a_classes':[],'b_classes':[],'relation':None,
                           'constraint':'one_to_one_leaf_pairs','alternatives_complete':False,
                           'hypotheses':[[ids[e] for e in plan] for plan in plans],
                           'status':'experimental_competing_hypotheses'}],
                  inspection_regions=regions,partial_alignment=evidence,
                  candidate_basis='unchanged v1 retrieval reference, not the experimental matching domain',
                  connectivity=connectivity(a,b,selected),hierarchy=hierarchy(a,b,selected))
    if options.matching_mode == 'regional':
        from .pieces import frontier_memberships
        result['hierarchy']['frontier_membership_hypotheses'] = frontier_memberships(a, b, plans)
        result['representative_selection'] = representative_selection
        from .exchange import population
        result['population_evidence'] = population(a, b, plans[-1] if plans else [])
    for side,view in [('a',a),('b',b)]:
        choices=defaultdict(list)
        for index, region in enumerate(regions):
            for p in region[side]: choices[p].append(index)
        opposite = 'b' if side == 'a' else 'a'
        counts=dict.fromkeys(('tentative','ambiguous','unresolved','unpaired','opaque'),0)
        rows=[]; sizes = {}
        for l in view.leaves:
            key = tuple(choices[l.path])
            if key not in sizes:
                sizes[key] = len(set().union(*(regions[k][opposite] for k in key)))
            n=sizes[key];state='opaque' if l.opaque else ('unresolved' if n==0 else 'tentative' if n==1 else 'ambiguous')
            counts[state]+=1;rows.append({'object':l.path,'status':state,'group':'qap','reason':'see_competing_hypotheses_and_structural_factors'})
        result[side].update(coverage=counts,disposition=rows)
    result['metrics']['seconds']['partial_alignment']=evidence['seconds']
    return result
