"""Experimental supplied-window comparison, separate from global correspondence."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import json
import math
import random
import re
import time

from .expand import expand
from .model import View, Options, InputScope, location
from .report import catalog, identity
from .scoped_core import Executor, counts, signature, digest


ALTERNATIVES = 'Unresolved; no unique leaf/net identity, exhaustive optimal explanations or historical edit claim.'


LIMITS = {'leaves_per_side': 64, 'nets_per_side': 64, 'counterparts_per_endpoint': 16,
          'cards': 12, 'charged_paths': 100}


def limits_for(options):
    return {'leaves_per_side': options.operator_max_leaves, 'nets_per_side': options.operator_max_nets,
            'counterparts_per_endpoint': options.operator_max_counterparts, 'cards': options.operator_max_cards,
            'charged_paths': options.operator_presentation_paths, 'retained_paths': options.operator_retained_paths}


def budget_details(window, limits):
    """All admission predicates, independent of their first-failure status."""
    graph=window['anonymous_input']; cc=counts(graph)
    base={s:set(window['members'][s])|set(window['supplied_scopes'][s]) for s in ('a','b')}
    measured={'leaves_per_side':{s:len(graph[s]['objects']) for s in ('a','b')},
              'nets_per_side':{s:graph[s]['net_count'] for s in ('a','b')},
              'counterparts_per_endpoint':{s:max((cc['b' if s=='a' else 'a'][sig] for sig in cc[s]),default=0) for s in ('a','b')},
              'internal_context_paths':sum(map(len,base.values())),
              'environment_context_paths':sum(len(base[s]|set(window['exterior'][s]['witness_paths'])) for s in ('a','b'))}
    reasons=[]
    if not window['admission']['expansion_complete']:reasons.append('incomplete_expansion')
    if any(window['admission']['opaque_paths'][s] for s in ('a','b')):reasons.append('opaque_scope_abstention')
    if measured['internal_context_paths']>limits.get('retained_paths',100):reasons.append('scope_path_budget_abstention')
    for field,reason in (('leaves_per_side','leaf_budget_abstention'),('nets_per_side','net_budget_abstention'),
                         ('counterparts_per_endpoint','counterpart_budget_abstention')):
        if max(measured[field].values())>limits[field]:reasons.append(reason)
    return measured,reasons


def admission_status(reasons):
    if not reasons:return None
    return 'domain_budget_abstention' if reasons[0] in ('leaf_budget_abstention','net_budget_abstention') else reasons[0]


def bounded_compare(a, b, *, top_a, top_b, options, scope_a, scope_b,
                    paths_a=(), paths_b=(), same_full_netlist=False):
    for paths in (paths_a, paths_b):
        if not isinstance(paths, (tuple, list)) or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError('operator paths must be nonempty path strings in a tuple/list; an empty tuple selects the supplied top')
    from .scoped_runtime import bounded
    return bounded({'a': a, 'b': b, 'top_a': top_a, 'top_b': top_b,
                    'paths_a': tuple(paths_a), 'paths_b': tuple(paths_b), 'options': options,
                    'scope_a': scope_a, 'scope_b': scope_b, 'same_full_netlist': same_full_netlist}, options)


def compare_batch(a, b, *, top_a, top_b, windows, options=None,
                  scope_a=None, scope_b=None, same_full_netlist=False):
    """Compare an ordered set of supplied windows with explicit batch-local reuse.

    ``windows`` is a sequence of mappings containing only ``paths_a`` and
    ``paths_b``.  The inputs, tops, scopes and options are fixed for the whole
    batch; callers start another batch when any of them changes.  Each returned
    report retains an independently encoded graph and proof.
    """
    options = options or Options(matching_mode='operator_scoped')
    scope_a, scope_b = scope_a or InputScope(), scope_b or InputScope()
    if options.matching_mode != 'operator_scoped':
        raise ValueError('operator batch requires matching_mode operator_scoped')
    normalized=[]
    if not isinstance(windows, (tuple, list)) or not windows:
        raise ValueError('operator batch windows must be a nonempty tuple/list')
    for window in windows:
        if not isinstance(window, dict) or set(window) - {'paths_a','paths_b'}:
            raise ValueError('each operator batch window contains only paths_a and paths_b')
        paths_a,paths_b=window.get('paths_a',()),window.get('paths_b',())
        for paths in (paths_a,paths_b):
            if not isinstance(paths,(tuple,list)) or any(not isinstance(p,str) or not p for p in paths):
                raise ValueError('batch paths must be nonempty strings in a tuple/list')
        normalized.append({'paths_a':tuple(paths_a),'paths_b':tuple(paths_b)})
    from .scoped_runtime import bounded_batch
    return bounded_batch({'a':a,'b':b,'top_a':top_a,'top_b':top_b,
                          'scope_a':scope_a,'scope_b':scope_b,'options':options,
                          'same_full_netlist':same_full_netlist,'windows':normalized}, options)


def compare_files(args, options, scope):
    """CLI parsing and normalization run inside the same killable worker."""
    from .scoped_runtime import bounded
    return bounded({'files': {'a': str(args.a), 'b': str(args.b) if args.b else None,
                             'format': args.format}, 'top_a': args.top_a if args.b else args.top,
                    'top_b': args.top_b if args.b else args.top,
                    'paths_a': tuple(args.path_a or ()), 'paths_b': tuple(args.path_b or ()),
                    'options': options, 'scope_a': scope, 'scope_b': scope,
                    'same_full_netlist': not bool(args.b)}, options)


def _empty_side(top, roots, reason):
    paths = list(roots) or [location((top or 'unselected',))]
    return {'objects': [], 'occurrences': [{'path': p, 'depth': len(p.split('/'))-1} for p in paths],
            'definitions': [], 'classes': [], 'disposition': [], 'coverage': {'unresolved': 0, 'opaque': 0},
            'diagnostics': [], 'unresolved': [{'reason': reason, 'region': p} for p in paths],
            'expansion_complete': False, 'expanded_leaf_count': 0, 'black_box_leaf_count': 0, 'max_depth': 0}


def incomplete_report(request, reason):
    options = request['options']
    result = {'schema_version': 1, 'algorithm': 'operator_scoped_exact_incidence_v1',
              'scope': {'comparison': 'operator_supplied_local_regions', 'top_a': request.get('top_a') or 'unselected',
                        'top_b': request.get('top_b') or 'unselected', 'same_full_netlist': request.get('same_full_netlist',False),
                        'knowledge': 'Supplied scope correspondence is input, never automatic discovery.'},
              'input_identity': {'kind': 'unavailable_incomplete_execution', 'a': None, 'b': None},
              'options': asdict(options), 'groups': [], 'pair_options': [], 'representative_pair_ids': [],
              'candidate_edges': [], 'connectivity': {'conditional_on_pair_ids': [], 'overlap': [],
              'unpaired_endpoints_a': [], 'unpaired_endpoints_b': [], 'meaning': 'No global endpoint correspondence is selected.'},
              'hierarchy': {'conditional_on_pair_ids': [], 'memberships': [], 'occurrence_options': [], 'definition_options': []},
              'metrics': {'screening_complete': False, 'seconds': {}},
              'operator_scoped': {'schema_version': 2, 'status': reason, 'certified_internal': False,
                                  'limits': limits_for(options), 'windows': [], 'cards': [], 'charged_paths': {'a': [], 'b': []},
                                  'charged_count': 0, 'resources': {}, 'global_correspondence': 'not_attempted',
                                  'meaning': 'Conditional local evidence, not identity, edit history or electrical equivalence.'}}
    for s in ('a', 'b'):
        result[s] = _empty_side(request.get('top_'+s), request.get('paths_'+s,()), reason)
    return result


def _select(data, top, paths, scope, options):
    views = [expand(data, top, scope, options, path=p) for p in dict.fromkeys(paths)] if paths else [expand(data, top, scope, options)]
    # Resolve aliases before any ownership/composition calculation.
    views = list({v.occurrences[0]['path']:v for v in views}.values())
    roots = [v.occurrences[0]['path'] for v in views]
    if any(not v.leaves and not v.budget_exhausted for v in views):
        raise ValueError('operator scope is empty; choose a represented block with leaves')
    # A contained selected root adds no membership. Still charge all supplied addresses.
    active = [v for v in views if not any(v.occurrences[0]['path'].startswith(p+'/') for p in roots if p != v.occurrences[0]['path'])]
    if len(active) == 1:
        return active[0], roots, [v.selection for v in views if v.selection]
    out = View(definitions={}, declared_subcircuits=set(), budget_exhausted=any(v.budget_exhausted for v in active))
    owners = defaultdict(set)
    for i, v in enumerate(active):
        physical = v.selection['physical_net_map'] if v.selection else {}
        for leaf in v.leaves:
            for n in leaf.nets.values(): owners[physical.get(n,n)].add(i)
    seen, occurrences = set(), set()
    for v in active:
        out.definitions.update(v.definitions); out.declared_subcircuits.update(v.declared_subcircuits)
        out.unresolved.extend(v.unresolved); out.diagnostics.extend(v.diagnostics)
        physical = v.selection['physical_net_map'] if v.selection else {}
        for leaf in v.leaves:
            if leaf.path in seen: continue
            seen.add(leaf.path); leaf = deepcopy(leaf)
            # Compose connections crossing supplied pieces, keeping other caller
            # aliases separate from within-piece internal structure.
            leaf.nets = {r: (physical.get(n,n) if len(owners[physical.get(n,n)])>1 else n) for r,n in leaf.nets.items()}
            index = len(out.leaves); out.leaves.append(leaf)
            for role,n in leaf.nets.items(): out.nets.setdefault(n,[]).append((index,role))
        for occurrence in v.occurrences:
            if occurrence['path'] not in occurrences:
                out.occurrences.append(occurrence); occurrences.add(occurrence['path'])
    return out, roots, [v.selection for v in views if v.selection]


def _atom(leaf):
    roles = [c.pin.casefold() for c in leaf.device.connections]
    if len(roles) != len(set(roles)):
        raise ValueError('case-fold terminal-role collision at '+leaf.path)
    if any(not isinstance(r,str) or not r for r in leaf.nets):
        raise ValueError('invalid terminal role at '+leaf.path)
    if leaf.black_box:
        cell, basis = leaf.black_box['cell'], leaf.black_box['pin_basis']
        if not isinstance(cell,str) or not cell or basis not in ('named','positional'):
            raise ValueError('invalid canonical black-box interface')
        if basis=='positional' and any(not re.fullmatch(r'@[1-9][0-9]*',r) for r in leaf.nets):
            raise ValueError('positional black-box terminals require explicit @N roles')
        cell = 'external:'+cell.casefold()
    else:
        refs = [(p.name.casefold(),p.value.casefold()) for p in leaf.device.parameters if p.name.casefold() in ('model','source_type')]
        cell, basis = 'primitive:'+json.dumps([leaf.device.type.casefold(),refs]), 'named'
    parameters = []
    for p in leaf.device.parameters:
        if not isinstance(p.name,str) or not isinstance(p.value,str):
            raise ValueError('canonical parameters must have string names/values')
        if leaf.device.black_box is not None or p.name.casefold() not in ('model','source_type','raw','unresolved_nets'):
            parameters.append({'name':p.name.casefold(),'value':p.value})
    # Deliberate whitelist. No definition, path, unresolved-net metadata or names.
    return {'cell':cell,'pin_basis':basis,'parameters':sorted(parameters,key=lambda p:(p['name'],p['value'])),
            'nets':{r.casefold():n for r,n in leaf.nets.items()}}


def encode(views):
    graph, addresses, net_addresses = {}, {}, {}
    for s, view in views.items():
        rows = list(view.leaves); random.Random('operator-scoped/'+s).shuffle(rows)
        addresses[s] = [l.path for l in rows]
        names = list(dict.fromkeys(n for leaf in rows for n in leaf.nets.values()))
        random.Random('operator-scoped/nets/'+s).shuffle(names)
        net_addresses[s] = names; indices = {n:i for i,n in enumerate(names)}
        objects = []
        for leaf in rows:
            atom = _atom(leaf); atom['nets'] = {r:indices[n] for r,n in atom['nets'].items()}; objects.append(atom)
        graph[s] = {'objects':objects,'net_count':len(names)}
    return graph, addresses, net_addresses


def facts(graph):
    cc = counts(graph); evidence = []; parameters = []; invfocus = {s:set() for s in ('a','b')}; inv = []
    for sig in sorted(cc['a'].keys()|cc['b'].keys()):
        if cc['a'][sig] != cc['b'][sig]:
            inv.append({'class':list(sig[:2])+[list(sig[2])],'a':cc['a'][sig],'b':cc['b'][sig]})
            for s in invfocus: invfocus[s].update(i for i,o in enumerate(graph[s]['objects']) if signature(o)==sig)
        elif cc['a'][sig]:
            values = {s:Counter(json.dumps(o['parameters'],sort_keys=True) for o in graph[s]['objects'] if signature(o)==sig) for s in ('a','b')}
            if values['a'] != values['b']:
                changed = {p for p in values['a'].keys()|values['b'].keys() if values['a'][p]!=values['b'][p]}
                focus = {s:[i for i,o in enumerate(graph[s]['objects']) if signature(o)==sig and json.dumps(o['parameters'],sort_keys=True) in changed] for s in ('a','b')}
                parameters.append({'kind':'parameter_multiset_residual','class':list(sig[:2])+[list(sig[2])], 'a':dict(values['a']),'b':dict(values['b']), 'focus':focus,
                                   'meaning':'Unequal literal parameter multisets in an equal-population class; values/expressions are not evaluated.'})
    if inv: evidence.append({'kind':'literal_inventory_or_interface_residual','value':inv,'focus':{s:sorted(v) for s,v in invfocus.items()},'meaning':'Literal cell/role inventory differs; replacement versus relabel is unknown.'})
    delta=len(graph['b']['objects'])-len(graph['a']['objects'])
    if delta: evidence.append({'kind':'represented_population_residual','value':delta,'focus':{s:list(range(len(graph[s]['objects']))) for s in ('a','b')},'meaning':'Represented population surplus, not identified historical additions/removals.'})
    return evidence, parameters


def terminal_focus(graph,q):
    netmap={int(a):b for a,b in q['netmap'].items()};touched={s:set() for s in ('a','b')};bad=[]
    for a,b in q['pairs']:
        for role,na in graph['a']['objects'][a]['nets'].items():
            nb=graph['b']['objects'][b]['nets'][role]
            if netmap.get(na)!=nb:
                bad.append({'a_leaf':a,'b_leaf':b,'role':role,'a_net':na,'b_net':nb})
                for s,n in (('a',na),('b',nb)):
                    touched[s].update(i for i,o in enumerate(graph[s]['objects']) if n in o['nets'].values())
    for a,b in q['pairs']:
        if a in touched['a'] or b in touched['b']:touched['a'].add(a);touched['b'].add(b)
    sigs={signature(graph[s]['objects'][i]) for s in touched for i in touched[s]}
    return {s:[i for i,o in enumerate(graph[s]['objects']) if signature(o) in sigs] for s in touched},bad


def validate_exterior(evidence):
    for s in ('a','b'):
        rows=evidence[s]['crossing_nets'];witnesses=evidence[s]['witness_paths']
        if evidence[s]['count']!=len(rows) or len({r['physical_net'] for r in rows})!=len(rows):
            raise ValueError('invalid exterior crossing-net count')
        for row in rows:
            if not set(row['outside_paths']) & set(witnesses):
                raise ValueError('missing exterior witness for crossing net')
        allowed={p for row in rows for p in row['outside_paths']}
        if not set(witnesses)<=allowed:
            raise ValueError('exterior witness is not a crossing endpoint')


def _exterior(data,top,view,roots,selections,scope,options):
    full=expand(data,top,scope,options)
    selected={l.path for l in view.leaves};physical={}
    for selection in selections:physical.update(selection['physical_net_map'])
    touched={physical.get(n,n) for leaf in view.leaves for n in leaf.nets.values()}
    crossing=[];witnesses=set()
    for n in sorted(touched):
        outside=sorted({full.leaves[i].path for i,r in full.nets.get(n,[]) if full.leaves[i].path not in selected})
        if outside:crossing.append({'physical_net':n,'outside_paths':outside});witnesses.add(outside[0])
    complete=not full.budget_exhausted and not any(l.opaque for l in full.leaves)
    return {'complete':complete,'crossing_nets':crossing,'count':len(crossing),
            'witness_paths':sorted(witnesses),'meaning':'Physical crossing nets reconstructed from represented full-top incidence; caller aliases are exterior context.'}


def _exterior_index(data, top, scope, options):
    full=expand(data,top,scope,options)
    paths={n:tuple(sorted({full.leaves[i].path for i,r in endpoints})) for n,endpoints in full.nets.items()}
    return {'paths_by_physical_net':paths,
            'complete':not full.budget_exhausted and not any(l.opaque for l in full.leaves)}


def _indexed_exterior(index,view,selections):
    selected={l.path for l in view.leaves};physical={}
    for selection in selections:physical.update(selection['physical_net_map'])
    touched={physical.get(n,n) for leaf in view.leaves for n in leaf.nets.values()}
    crossing=[];witnesses=set()
    for n in sorted(touched):
        outside=[p for p in index['paths_by_physical_net'].get(n,()) if p not in selected]
        if outside:crossing.append({'physical_net':n,'outside_paths':outside});witnesses.add(outside[0])
    return {'complete':index['complete'],'crossing_nets':crossing,'count':len(crossing),
            'witness_paths':sorted(witnesses),'meaning':'Physical crossing nets reconstructed from represented full-top incidence; caller aliases are exterior context.'}


def _prepare_batch(request):
    start=time.monotonic();a,b=request['a'],request['b'];options=request['options']
    identities={'a':identity(a),'b':identity(b)};identity_done=time.monotonic()
    exterior={s:_exterior_index(data,request['top_'+s],request['scope_'+s],options)
              for s,data in (('a',a),('b',b))}
    prepared={'identities':identities,'exterior':exterior}
    key={'input_identity':identities,'top_a':request['top_a'],'top_b':request['top_b'],
         'scope_a':asdict(request['scope_a']),'scope_b':asdict(request['scope_b']),
         'options':asdict(options)}
    prepared['key_sha256']=digest(key)
    prepared['phase_seconds']={'input_identity':identity_done-start,
                               'full_top_exterior_index':time.monotonic()-identity_done}
    return prepared


def _terminal_evidence(window):
    proof=window['hypotheses'];graph=window['anonymous_input']
    if proof.get('certified') and proof['K']:
        full=proof['maximum_coverage'];lower=proof['one_pair_less']
        window['coverage_sensitivity']={'K':proof['K'],'error_at_K':full['error'],'error_at_K_minus_1':lower['error'],
                                       'loss_of_one_pair_removes_residual':full['error']>0 and lower['error']==0}
        if full['error']:
            focus,bad=terminal_focus(graph,full)
            window['evidence'].append({'kind':'necessary_internal_terminal_residual','focus':focus,'terminal_mismatches':bad,
                                      'value':window['coverage_sensitivity'],
                                      'meaning':'Necessary at maximum literal-compatible coverage; this focus is one optimum plus endpoint/compatible rivals, not unique edit identity.'})


def _present(window, parameters_enabled, limits=None):
    """Deterministic indivisible cards, reconstructed also when reading saved JSON."""
    limits=LIMITS if limits is None else limits
    window['cards']=[];window['omitted']=[]
    addresses=window['members'];roots=window['supplied_scopes'];ext=window['exterior']
    charge={s:sorted(set(addresses[s])|set(roots[s])) for s in ('a','b')}
    def add_card(lane,evidence,charged,focus=None):
        combined={s:set(charged[s])|{p for c in window['cards'] for p in c['charged_paths'][s]} for s in ('a','b')}
        if sum(map(len,combined.values()))>limits['charged_paths'] or len(window['cards'])>=limits['cards']:
            window['omitted'].append({'lane':lane,'reason':'full_support_path_budget'});return
        focus=focus or {s:sorted({addresses[s][i] for e in evidence for i in e.get('focus',{}).get(s,[])}) for s in ('a','b')}
        window['cards'].append({'id':window['id']+':'+lane,'window_id':window['id'],'lane':lane,'channel':'environment' if lane=='environment' else 'internal_content','evidence':evidence,'focus_paths':focus,
                               'charged_paths':charged,'charged_count':sum(len(set(x)) for x in charged.values()),'status':'conditional',
                               'identity_claim':False,'uniqueness_claim':False,'confirmed_design_change_claim':False,'alternatives':window['alternatives']})
    if 'retained_paths' in limits:
        window['retention']={'internal_context_paths':sum(map(len,charge.values())),
                             'environment_context_paths':sum(len(set(charge[s])|set(ext[s]['witness_paths'])) for s in ('a','b')),
                             'limit':limits['retained_paths'],
                             'meaning':'Evidence-lane support budgets; raw source catalogs and exterior endpoint records remain audit data.'}
        window['retention']['internal_within_budget']=window['retention']['internal_context_paths']<=limits['retained_paths']
        window['retention']['environment_within_budget']=window['retention']['environment_context_paths']<=limits['retained_paths']
    if window['evidence']:add_card('architecture',window['evidence'],charge)
    if window['parameter_evidence'] and parameters_enabled:add_card('parameter_detail',window['parameter_evidence'],charge)
    if all(ext[s]['complete'] for s in ('a','b')):
        if ext['a']['count']!=ext['b']['count']:
            add_card('environment',[{'kind':'represented_physical_boundary_count','a':ext['a']['count'],'b':ext['b']['count'],'meaning':'Separate exterior context; equal counts would not establish unchanged attachment identity.'}],
                     {s:sorted(set(charge[s])|set(ext[s]['witness_paths'])) for s in ('a','b')},roots)
    else:window['omitted'].append({'lane':'environment','reason':'incomplete_full_top_exterior_incidence'})


def _execute(request, prepared=None):
    start=time.monotonic();options=request['options'];deadline=start+options.operator_time_limit
    phases={};phase_start=start;limits=limits_for(options)
    def phase(name):
        nonlocal phase_start
        now=time.monotonic();phases[name]=now-phase_start;phase_start=now
    if 'files' in request:
        from .cli import load_netlist,choose_top
        files=request['files'];a=load_netlist(files['a'],files['format']);b=load_netlist(files['b'],files['format']) if files['b'] else a
        request={**request,'a':a,'b':b,'top_a':choose_top(a,request['top_a'],'--top-a' if files['b'] else '--top'),
                 'top_b':choose_top(b,request['top_b'],'--top-b' if files['b'] else '--top')}
    phase('load')
    a,b=request['a'],request['b'];views={};roots={};selections={}
    for s,data in (('a',a),('b',b)):
        views[s],roots[s],selections[s]=_select(data,request['top_'+s],request.get('paths_'+s,()),request['scope_'+s],options)
    if options.black_box_missing:
        from .blackbox import reconcile
        reconcile(views['a'],views['b'])
        # In this mode unequal literal interfaces are inventory evidence. Their
        # disjoint role signatures forbid invented cross-width correspondence,
        # without making unrelated represented leaves opaque.
        for view in views.values():
            for leaf in view.leaves:
                if leaf.opaque == 'incompatible_black_box_interfaces':
                    leaf.opaque = None
    phase('selection_and_interfaces')
    graph,addresses,net_addresses=encode(views)
    charge={s:sorted(set(addresses[s])|set(roots[s])) for s in ('a','b')};cost=sum(map(len,charge.values()))
    result=incomplete_report(request,'pending');identities=prepared['identities'] if prepared else {'a':identity(a),'b':identity(b)}
    result['input_identity']={'kind':'retained_canonical_data_sha256',**identities}
    result['scope'].update(a=asdict(request['scope_a']),b=asdict(request['scope_b']),global_net_declarations_complete=request['scope_a'].globals_complete and request['scope_b'].globals_complete)
    for s,view in views.items():
        side=catalog(view);side.update(classes=[],coverage={'unresolved':sum(not l.opaque for l in view.leaves),'opaque':sum(bool(l.opaque) for l in view.leaves)},
            disposition=[{'object':l.path,'status':'opaque' if l.opaque else 'unresolved','group':None,'reason':l.opaque or 'global_identity_not_attempted_in_operator_scoped_mode'} for l in view.leaves])
        if view.selection:side['selection']=view.selection
        result[s]=side
    phase('encoding_and_catalogs')
    ext={};unknown=[]
    for s,data in (('a',a),('b',b)):
        ext[s]=(_indexed_exterior(prepared['exterior'][s],views[s],selections[s]) if prepared else
                _exterior(data,request['top_'+s],views[s],roots[s],selections[s],request['scope_'+s],options))
    validate_exterior(ext)
    phase('exterior_incidence')
    window={'id':'local0','supplied_scopes':roots,'scope_correspondence':'operator input; not discovered','members':addresses,'net_addresses':net_addresses,
            'selections':selections,'anonymous_input':graph,'input_sha256':digest(graph),'full_member_scope_charge':cost,'exterior':ext,
            'alternatives':ALTERNATIVES,
            'global_pair_ids':[],'hypotheses':{},'evidence':[],'parameter_evidence':[],'cards':[],'omitted':[],
            'admission':{'expansion_complete':all(not v.budget_exhausted for v in views.values()),
                         'opaque_paths':{s:[l.path for l in views[s].leaves if l.opaque] for s in ('a','b')}},
            'interface_limitations':{s:[u for u in views[s].unresolved if u['reason']=='incompatible_black_box_interfaces'] for s in ('a','b')}}
    measured,reasons=budget_details(window,limits)
    window['admission'].update(observed=measured,reasons=reasons)
    status=admission_status(reasons)
    if not any(r in reasons for r in ('incomplete_expansion','opaque_scope_abstention','scope_path_budget_abstention')):
        window['evidence'],window['parameter_evidence']=facts(graph)
    phase('admission_and_facts')
    if status is None:
        proof=Executor(graph,deadline,options.operator_query_seconds).run()
        window['hypotheses']=proof;status='certified' if proof['certified'] else 'proof_budget_abstention'
    phase('proofs')
    window['status']=status
    _terminal_evidence(window)
    _present(window, options.operator_parameters,limits)
    phase('presentation')
    used={s:sorted({p for c in window['cards'] for p in c['charged_paths'][s]}) for s in ('a','b')}
    extension=result['operator_scoped'];extension.update(status=status,certified_internal=status=='certified',windows=[window],cards=window['cards'],charged_paths=used,charged_count=sum(map(len,used.values())))
    extension['parameter_detail_enabled']=options.operator_parameters
    extension['resources'].update(core_seconds=time.monotonic()-start,phase_seconds=phases,query_seconds=options.operator_query_seconds,solver='scipy.optimize.milp/HiGHS; mathematical attaining-bound certificates first',cold_start=prepared is None,worker_count=1,
                                  batch_reuse_key_sha256=prepared['key_sha256'] if prepared else None)
    result['metrics']['seconds']['operator_scoped']=time.monotonic()-start
    if views['a'].selection and views['b'].selection:
        from .boundary import boundary_report
        result['boundary']=boundary_report(views['a'],views['b'],result)
        result['boundary']['correspondence']='unresolved; local witnesses never become global pin hypotheses'
        if not request.get('same_full_netlist'):
            result['boundary']['outer_net_relation']='Side-local context only; net spelling in different inputs is not identity.'
    return result


def _execute_batch(request):
    start=time.monotonic();prepared=_prepare_batch(request);results=[]
    for number,window in enumerate(request['windows']):
        item={**request,**window}
        item.pop('windows',None)
        result=_execute(item,prepared)
        result['operator_scoped']['resources']['batch_window_index']=number
        results.append(result)
    return {'schema_version':1,'kind':'operator_scoped_batch_v1','results':results,
            'reuse':{'scope':'this_batch_only','key_sha256':prepared['key_sha256'],
                     'input_identity':prepared['identities'],'window_count':len(results),
                     'meaning':'Only immutable input identity and full-top exterior incidence are reused; every window has its own selection, anonymous graph and proof.'},
            'resources':{'preparation_phase_seconds':prepared['phase_seconds'],
                         'core_seconds':time.monotonic()-start,'worker_count':1}}


def validate_saved_extension(extension):
    try:
        _validate_saved_extension(extension)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('malformed operator_scoped saved evidence') from exc


def _finite_saved_number(value):
    try:
        finite=type(value) in (int,float) and math.isfinite(value)
    except OverflowError:
        finite=False
    if not finite:
        raise ValueError('non-finite or invalid local optimality number')


def _validate_saved_extension(extension):
    """Validate local witnesses and indivisible path charges when viewing JSON."""
    from .scoped_core import validate_witness, capacity_bound, cardinality
    if not isinstance(extension,dict) or extension.get('schema_version') not in (1,2) or not isinstance(extension.get('windows'),list) or not isinstance(extension.get('cards'),list):
        raise ValueError('invalid operator_scoped extension')
    limits=extension.get('limits');version=extension['schema_version']
    expected_keys=set(LIMITS)|({'retained_paths'} if version==2 else set())
    if (not isinstance(limits,dict) or set(limits)!=expected_keys or
            any(type(v) is not int or v<=0 for v in limits.values()) or
            (version==1 and limits!=LIMITS) or
            (version==2 and limits['charged_paths']>limits['retained_paths']) or
            extension.get('global_correspondence')!='not_attempted'):
        raise ValueError('invalid local contract/limits')
    if type(extension.get('certified_internal')) is not bool:
        raise ValueError('invalid local certification flag')
    if not extension['windows']:
        allowed={'deadline_exhausted','memory_budget_exhausted','worker_memory_exhaustion',
                 'worker_terminated_before_complete_result','serialized_result_budget_exhausted'}
        if extension['status'] not in allowed or extension['certified_internal'] or extension['cards']:
            raise ValueError('inconsistent incomplete local status/certification')
    elif len(extension['windows'])!=1 or type(extension.get('parameter_detail_enabled')) is not bool:
        raise ValueError('invalid local window portfolio')
    window_by_id={w['id']:w for w in extension['windows']}
    if len(window_by_id)!=len(extension['windows']):raise ValueError('duplicate local window ID')
    for window in window_by_id.values():
        validate_exterior(window['exterior']);graph=window['anonymous_input'];proof=window.get('hypotheses',{})
        if digest(graph)!=window['input_sha256']:raise ValueError('local input hash mismatch')
        if not proof:continue
        _finite_saved_number(proof['K'])
        k=cardinality(graph)
        if proof['K']!=k or not proof.get('weighted') or not proof.get('maximum_coverage') or bool(proof.get('one_pair_less'))!=bool(k):
            raise ValueError('local certification missing a coverage prerequisite')
        expected_certified=all(q['status']=='optimal' for q in (proof['weighted'],proof['maximum_coverage'],proof.get('one_pair_less')) if q)
        if proof.get('certified') is not expected_certified:
            raise ValueError('inconsistent local proof certification')
        for name in ('weighted','maximum_coverage','one_pair_less'):
            q=proof.get(name)
            if not q:continue
            for field in ('coverage','error','weighted_cost','lower_bound','requested_coverage'):
                if field in q and q[field] is not None:_finite_saved_number(q[field])
            for field,value in q.get('certificate',{}).items():
                if field!='kind' and value is not None:_finite_saved_number(value)
            if 'pairs' not in q:
                if q.get('status')=='optimal':raise ValueError('optimal local result has no incidence witness')
                continue
            validate_witness(graph,q,None if name=='weighted' else proof['K']-(name=='one_pair_less'))
            if q.get('status')=='optimal':
                kinds=({'scipy_highs_milp','exhaustive_cardinality_partition'} if name=='weighted' else
                       {'scipy_highs_milp','attained_terminal_capacity_bound','nonnegative_empty_witness',
                        'nonnegative_restricted_witness','nonnegative_feasible_witness'})
                if q.get('proof') not in kinds:raise ValueError('unknown local optimality certificate')
                value=q['weighted_cost'] if name=='weighted' else q['error']
                bound=q.get('lower_bound')
                _finite_saved_number(bound);_finite_saved_number(value)
                if abs(bound-value)>1e-6:raise ValueError('invalid local optimality bound')
                if q.get('proof')=='scipy_highs_milp' and q.get('solver_status')!=0:raise ValueError('missing optimal solver status')
            if q.get('proof')=='attained_terminal_capacity_bound':
                wanted=capacity_bound(graph,q['coverage'])
                if q['certificate']!=wanted or q['error']!=wanted['lower_bound']:raise ValueError('invalid terminal-capacity certificate')
            if q.get('proof') in ('nonnegative_empty_witness','nonnegative_restricted_witness','nonnegative_feasible_witness') and q['error']!=0:
                raise ValueError('invalid nonnegative zero certificate')
        weighted=proof.get('weighted',{})
        if weighted.get('proof')=='exhaustive_cardinality_partition':
            k=proof['K'];full=proof['maximum_coverage'];lower=proof.get('one_pair_less')
            base=3*(sum(len(graph[s]['objects']) for s in ('a','b'))-2*k)
            costs=[full['weighted_cost']]+([lower['weighted_cost']] if lower else [])+([base+12] if k>=2 else [])
            expected={'K':k,'full_cost':full['weighted_cost'],'one_less_cost':lower['weighted_cost'] if lower else None,'smaller_cost_lower_bound':base+12 if k>=2 else None}
            if weighted['certificate']!=expected or weighted['weighted_cost']!=min(costs) or weighted['lower_bound']!=min(costs):
                raise ValueError('invalid weighted cardinality certificate')
        if proof.get('certified') and not all(q['status']=='optimal' for q in (proof['weighted'],proof['maximum_coverage'],proof.get('one_pair_less')) if q):
            raise ValueError('local certification missing an optimality prerequisite')
    # Reconstruct evidence, focus, lanes and status rather than trusting any of
    # the report's duplicated labels. This is consistency checking, not a
    # signature/authenticity claim for an arbitrarily rewritten source report.
    expected_cards=[]
    for window in window_by_id.values():
        graph=window['anonymous_input'];proof=window['hypotheses'];admission=window['admission']
        if window['alternatives']!=ALTERNATIVES or window['scope_correspondence']!='operator input; not discovered':
            raise ValueError('invalid local scope/alternative meaning')
        cost=sum(len(set(window['members'][s])|set(window['supplied_scopes'][s])) for s in ('a','b'))
        if window['full_member_scope_charge']!=cost or window['global_pair_ids']:
            raise ValueError('invalid local scope charge/identity contract')
        if any(len(window['members'][s])!=len(graph[s]['objects']) or len(set(window['members'][s]))!=len(window['members'][s]) for s in ('a','b')):
            raise ValueError('invalid local membership addresses')
        measured,reasons=budget_details(window,limits)
        if version==2 and (admission.get('observed')!=measured or admission.get('reasons')!=reasons):
            raise ValueError('local admission reasons/counts do not reconstruct')
        status=admission_status(reasons)
        if status is None:
            if not proof:raise ValueError('local proof status missing')
            status='certified' if proof['certified'] else 'proof_budget_abstention'
        if window['status']!=status or extension['status']!=status or extension['certified_internal'] is not (status=='certified'):
            raise ValueError('inconsistent local status/certification')
        if status not in ('certified','proof_budget_abstention') and proof:
            raise ValueError('proof present outside admitted local domain')
        expected=deepcopy(window);expected['evidence']=[];expected['parameter_evidence']=[]
        expected.pop('coverage_sensitivity',None)
        if status not in ('incomplete_expansion','opaque_scope_abstention','scope_path_budget_abstention'):
            expected['evidence'],expected['parameter_evidence']=facts(graph)
        _terminal_evidence(expected)
        for key in ('evidence','parameter_evidence','coverage_sensitivity'):
            if window.get(key)!=expected.get(key):raise ValueError('local evidence/focus does not reconstruct from original incidence and proofs')
        _present(expected,extension['parameter_detail_enabled'],limits)
        if window['cards']!=expected['cards'] or window['omitted']!=expected['omitted'] or window.get('retention')!=expected.get('retention'):
            raise ValueError('local card lane/evidence/focus/charge does not match retained window evidence')
        expected_cards.extend(expected['cards'])
    if extension['cards']!=expected_cards:
        raise ValueError('local card lane/evidence/focus/charge does not match complete retained window cards')
    used={s:set() for s in ('a','b')}
    for card in extension['cards']:
        window=window_by_id.get(card.get('window_id'))
        if window is None or card['identity_claim'] or card['uniqueness_claim'] or card['confirmed_design_change_claim']:
            raise ValueError('invalid local conditional card')
        for s in ('a','b'):
            expected=set(window['members'][s])|set(window['supplied_scopes'][s])
            if card['lane']=='environment':expected.update(window['exterior'][s]['witness_paths'])
            if set(card['charged_paths'][s])!=expected or not set(card['focus_paths'][s])<=expected:
                raise ValueError('incomplete local context/support charge')
            used[s].update(expected)
        if card['charged_count']!=sum(len(set(card['charged_paths'][s])) for s in ('a','b')):raise ValueError('incorrect card charge')
    if len(extension['cards'])>limits['cards'] or sum(map(len,used.values()))>limits['charged_paths'] or extension['charged_count']!=sum(map(len,used.values())):
        raise ValueError('invalid local presentation budget')
    if any(set(extension['charged_paths'][s])!=used[s] for s in ('a','b')):raise ValueError('invalid local union charge')
