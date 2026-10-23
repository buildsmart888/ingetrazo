"""Source-locked accepted v0.7 beam stages.

No AST, exec, generated-source evaluation, or GUI mutation occurs here.
Each phase accepts an explicit runtime domain and shared build state.
"""
from __future__ import annotations

def prepare(domain, state):
    CORNER_STEPS = domain.CORNER_STEPS
    Layer = domain.Layer
    SPANS_M = domain.SPANS_M
    STIRRUP_HOOK_DEG = domain.STIRRUP_HOOK_DEG
    _fillet_polyline = domain._fillet_polyline
    allocate_bar_to_spans = domain.allocate_bar_to_spans
    check_inputs = domain.check_inputs
    check_main_and_extra_levels = domain.check_main_and_extra_levels
    check_tie_mesh_envelope = domain.check_tie_mesh_envelope
    classic_group = domain.classic_group
    instanced_group = domain.instanced_group
    make_stirrup_prototype = domain.make_stirrup_prototype
    math = domain.math
    scene = domain.scene
    steel_kg_per_m = domain.steel_kg_per_m
    stirrup_bend_radius = domain.stirrup_bend_radius
    stirrup_shape_vertices = domain.stirrup_shape_vertices
    supports_x = domain.supports_x
    check_inputs()
    x_support=supports_x()
    X=x_support[-1]
    ztop,zbot,z_extra_top,z_extra_bot=check_main_and_extra_levels()
    tie_proto,tie_length,tie_axial_shift=make_stirrup_prototype()
    tie_bounds=check_tie_mesh_envelope(tie_proto,tie_axial_shift)
    tie_r=stirrup_bend_radius()
    tie_path=_fillet_polyline(stirrup_shape_vertices()[0],tie_r,CORNER_STEPS)

    layer_specs={
        'concrete':'GO | Concrete',
        'top':'GO | Main Top',
        'bottom':'GO | Main Bottom',
        'extra_top':'GO | Extra Top',
        'extra_bottom':'GO | Extra Bottom',
        'stirrup':'GO | Stirrups',
        'formwork':'GO | Formwork',
        'support':'GO | Supports (reference)',
    }
    for lname in layer_specs.values():
        if not any(ly.name==lname for ly in scene.layers):
            scene.layers.append(Layer(lname))
    items=[]; bar_meta={}; form_meta={}; stirrup_stations=[]; bar_geom=[]
    extra_hook_entries=[]; support_references=[]
    span_mass_by_kind=[{} for _ in SPANS_M]
    bar_locations={}
    span_concrete_m3=[]
    def add(m,name,kind,tag,layer=None,position=None,info=None):
        ly=layer or layer_specs[kind]
        if position is not None:
            g=instanced_group(m,name,tag,ly,*position,metadata={**(info or {}),'kind':kind})
        else:
            g=classic_group(m,name,tag,ly,metadata={**(info or {}),'kind':kind})
        items.append(g)
        return g
    def note_rebar(name,kind,db,length,mark,span_index=0,extra=None,centerline=None):
        allocation=(allocate_bar_to_spans(centerline) if centerline is not None
                    else [length if j==span_index-1 else 0.0 for j in range(len(SPANS_M))])
        if not math.isclose(sum(allocation),length,rel_tol=0,abs_tol=0.000005):
            raise ValueError('Rebar per-span quantity allocation does not reconcile for '+name)
        meta={'kind':kind,'diameter_mm':db,'length_m':length,
              'weight_kg':steel_kg_per_m(db)*length,'mark':mark,
              'span_index':span_index,
              'hook_deg':STIRRUP_HOOK_DEG if kind=='stirrup' else 90,
              'allocation_length_m_by_span':[round(v,9) for v in allocation],
              'allocation_weight_kg_by_span':[round(steel_kg_per_m(db)*v,9) for v in allocation],
              **(extra or {})}
        for j,allocated in enumerate(allocation):
            record=span_mass_by_kind[j]
            record[kind]=record.get(kind,0.0)+steel_kg_per_m(db)*allocated
        return meta

    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

def create_parts(domain, state):
    B = domain.B
    BEAM_ID = domain.BEAM_ID
    BOTTOM_COUNT = domain.BOTTOM_COUNT
    BOTTOM_DB_MM = domain.BOTTOM_DB_MM
    CORNER_STEPS = domain.CORNER_STEPS
    END_COVER = domain.END_COVER
    H = domain.H
    PLYWOOD_THICKNESS = domain.PLYWOOD_THICKNESS
    SHOW_SUPPORT_MARKERS = domain.SHOW_SUPPORT_MARKERS
    SPANS_M = domain.SPANS_M
    SPECIAL_BOTTOM_COUNT = domain.SPECIAL_BOTTOM_COUNT
    SPECIAL_BOTTOM_DB_MM = domain.SPECIAL_BOTTOM_DB_MM
    SPECIAL_BOTTOM_FRACTION = domain.SPECIAL_BOTTOM_FRACTION
    SPECIAL_BOTTOM_HOOK_TAIL_MM = domain.SPECIAL_BOTTOM_HOOK_TAIL_MM
    SPECIAL_TOP_COUNT = domain.SPECIAL_TOP_COUNT
    SPECIAL_TOP_DB_MM = domain.SPECIAL_TOP_DB_MM
    SPECIAL_TOP_FRACTION = domain.SPECIAL_TOP_FRACTION
    SPECIAL_TOP_HOOK_TAIL_MM = domain.SPECIAL_TOP_HOOK_TAIL_MM
    STIRRUP_DB_MM = domain.STIRRUP_DB_MM
    STIRRUP_HOOK_DEG = domain.STIRRUP_HOOK_DEG
    STIRRUP_HOOK_TAIL_MM = domain.STIRRUP_HOOK_TAIL_MM
    SUPPORT_WIDTH_M = domain.SUPPORT_WIDTH_M
    TOP_COUNT = domain.TOP_COUNT
    TOP_DB_MM = domain.TOP_DB_MM
    V = domain.V
    _fillet_polyline = domain._fillet_polyline
    check_extra_hook_clashes = domain.check_extra_hook_clashes
    db_m = domain.db_m
    get_span_tie_config = domain.get_span_tie_config
    inner_special_bar_positions = domain.inner_special_bar_positions
    make_longitudinal = domain.make_longitudinal
    make_special_bar = domain.make_special_bar
    nominal_steel_band_positions = domain.nominal_steel_band_positions
    solid_box = domain.solid_box
    span_stirrups = domain.span_stirrups
    support_reference_solid = domain.support_reference_solid
    tie_bar_clearance_mm = domain.tie_bar_clearance_mm
    X = state.X
    add = state.add
    bar_geom = state.bar_geom
    bar_locations = state.bar_locations
    bar_meta = state.bar_meta
    extra_hook_entries = state.extra_hook_entries
    form_meta = state.form_meta
    note_rebar = state.note_rebar
    span_concrete_m3 = state.span_concrete_m3
    stirrup_stations = state.stirrup_stations
    support_references = state.support_references
    tie_length = state.tie_length
    tie_path = state.tie_path
    tie_proto = state.tie_proto
    tie_r = state.tie_r
    x_support = state.x_support
    z_extra_bot = state.z_extra_bot
    z_extra_top = state.z_extra_top
    zbot = state.zbot
    ztop = state.ztop
    # Concrete and formwork are intentionally split per span, as quantities
    # belong to the piece between support centre-lines; no end caps in BOQ.
    conc_color=(0.66,0.69,0.72)
    for span_i,(x0,x1) in enumerate(zip(x_support[:-1],x_support[1:]),1):
        Ls=x1-x0
        span_concrete_m3.append(Ls*B*H)
        add(solid_box(x0,-B/2,0,x1,B/2,H,conc_color,0.40),
            f'{BEAM_ID}-Concrete-S{span_i:02d}','concrete','IfcBeam',
            info={'gross_volume_m3':Ls*B*H,'span_index':span_i})
        wood=(0.60,0.43,0.27)
        t=PLYWOOD_THICKNESS
        for part,box,area in [
            ('Soffit',(x0,-B/2,-t,x1,B/2,0),B*Ls),
            ('Side-L',(x0,-B/2-t,0,x1,-B/2,H),H*Ls),
            ('Side-R',(x0,B/2,0,x1,B/2+t,H),H*Ls)]:
            name=f'{BEAM_ID}-Form-S{span_i:02d}-{part}'
            add(solid_box(*box,wood,0.18),name,'formwork','IfcBuildingElementProxy',
                info={'span_index':span_i,'contact_area_m2':area})
            form_meta[name]=area

    # Visual-only support columns at centre-line stations. Not included in
    # takeoff/IFC because actual column levels, reinforcement and concrete
    # outside the beam are outside the defined structural input scope.
    if SHOW_SUPPORT_MARKERS:
        for pi,x in enumerate(x_support,1):
            solid=support_reference_solid(x)
            reference_name=f'{BEAM_ID}-SupportReference-P{pi:02d}'
            add(solid,reference_name,'support',None,
                info={'kind':'support','support_index':pi,'x_centre_m':x,
                      'reference_only':True,'excluded_from_boq_ifc':True})
            support_references.append({'index':pi,'x_centre_m':x,'width_m':SUPPORT_WIDTH_M,
                                       'left_face_x_m':x-SUPPORT_WIDTH_M/2,
                                       'right_face_x_m':x+SUPPORT_WIDTH_M/2})

    # Main bars are CONTINUOUS through ALL internal supports.
    for kind,count,dmm,z,hook_dir,color in [
        ('top',TOP_COUNT,TOP_DB_MM,ztop,-1,(0.79,0.40,0.35)),
        ('bottom',BOTTOM_COUNT,BOTTOM_DB_MM,zbot,+1,(0.27,0.43,0.78))]:
        (proto,length),hook_len,bend_r=make_longitudinal(
            END_COVER,X-END_COVER,dmm,z,hook_dir,color,True)
        ypos=nominal_steel_band_positions(count,dmm,z,tie_r,tie_path)
        bar_locations[kind]={'y_m':ypos,'z_m':z,'minimum_tie_clearance_mm':
            min(tie_bar_clearance_mm(y,z,dmm,tie_path) for y in ypos)}
        for index,y in enumerate(ypos,1):
            name=f'{BEAM_ID}-Main-{kind}-{index:02d}'
            mark=f'{BEAM_ID}-M{kind.upper()}-DB{dmm}'
            main_virtual=[V(END_COVER,0,z+hook_dir*hook_len),V(END_COVER,0,z),
                          V(X-END_COVER,0,z),V(X-END_COVER,0,z+hook_dir*hook_len)]
            main_bent=_fillet_polyline(main_virtual,bend_r,CORNER_STEPS)
            info=note_rebar(name,kind,dmm,length,mark,extra={
                'shape':'GO-M90','end_hooks':'90deg-both-ends',
                'bend_radius_m':bend_r,'hook_length_nominal_m':hook_len},
                centerline=main_bent)
            add(proto,name,kind,'IfcReinforcingBar',position=(0,y,0),info=info)
            bar_meta[name]=info
            bar_geom.append({'name':name,'kind':kind,'diameter_mm':dmm,
                'mark':mark,'mesh':proto,'offset':(0,y,0),
                'span_index':0,'support_index':0,
                'points':[V(v.x(),v.y()+y,v.z()) for v in main_bent]})

    # Special TOP bars over each internal/external support.
    # BOTH ends: 90deg downward with explicit, measurable straight tails.
    if SPECIAL_TOP_COUNT:
        dmm=SPECIAL_TOP_DB_MM
        ypos=inner_special_bar_positions(SPECIAL_TOP_COUNT,dmm,z_extra_top,tie_path)
        bar_locations['extra_top']={'y_m':ypos,'z_m':z_extra_top,
            'minimum_tie_clearance_mm':min(tie_bar_clearance_mm(y,z_extra_top,dmm,tie_path) for y in ypos)}
        for support_index,sx in enumerate(x_support):
            leftspan=SPANS_M[support_index-1] if support_index>0 else None
            rightspan=SPANS_M[support_index] if support_index<len(SPANS_M) else None
            xa=sx-(leftspan or 0)*SPECIAL_TOP_FRACTION
            xb=sx+(rightspan or 0)*SPECIAL_TOP_FRACTION
            # At external supports, show schematic hooked anchorage within
            # the beam cover; column anchorage checks are not performed.
            if support_index==0:
                xa=max(xa,END_COVER+db_m(dmm)/2)
            if support_index==len(SPANS_M):
                xb=min(xb,X-END_COVER-db_m(dmm)/2)
            if xb-xa<0.15:
                raise ValueError('Extra top support bar too short for 2 hooked ends')
            proto,length,centerline,bend_r=make_special_bar(
                xa,xb,dmm,z_extra_top,-1,SPECIAL_TOP_HOOK_TAIL_MM,(0.86,0.34,0.23))
            for j,y in enumerate(ypos,1):
                name=f'{BEAM_ID}-TopExtra-P{support_index+1:02d}-{j:02d}'
                mark=f'{BEAM_ID}-ET-P{support_index+1:02d}-DB{dmm}'
                worldline=[V(v.x(),v.y()+y,v.z()) for v in centerline]
                info=note_rebar(name,'extra_top',dmm,length,mark,
                    extra={'support_index':support_index+1,'shape':'GO-ET-90-2Ends',
                           'end_hooks':'90deg-both-ends-down',
                           'tail_straight_after_bend_mm':SPECIAL_TOP_HOOK_TAIL_MM,
                           'bend_radius_centerline_mm':bend_r*1000,
                           'start_m':xa,'end_m':xb},centerline=worldline)
                add(proto,name,'extra_top','IfcReinforcingBar',position=(0,y,0),info=info)
                bar_meta[name]=info
                extra_hook_entries.append({'name':name,'kind':'extra_top','db_mm':dmm,
                    'points':worldline,'xmin':xa,'xmax':xb})
                bar_geom.append({'name':name,'kind':'extra_top','diameter_mm':dmm,
                    'mark':mark,'mesh':proto,'offset':(0,y,0),
                    'span_index':0,'support_index':support_index+1,
                    'points':worldline})

    # Special BOTTOM bars centred at each SPAN.
    # BOTH ends: 90deg upward, with cut-off gap from special TOP bars.
    if SPECIAL_BOTTOM_COUNT:
        dmm=SPECIAL_BOTTOM_DB_MM
        ypos=inner_special_bar_positions(SPECIAL_BOTTOM_COUNT,dmm,z_extra_bot,tie_path)
        bar_locations['extra_bottom']={'y_m':ypos,'z_m':z_extra_bot,
            'minimum_tie_clearance_mm':min(tie_bar_clearance_mm(y,z_extra_bot,dmm,tie_path) for y in ypos)}
        for span_i,(x0,x1) in enumerate(zip(x_support[:-1],x_support[1:]),1):
            length_target=(x1-x0)*SPECIAL_BOTTOM_FRACTION
            xa=(x0+x1-length_target)/2
            xb=xa+length_target
            proto,length,centerline,bend_r=make_special_bar(
                xa,xb,dmm,z_extra_bot,+1,SPECIAL_BOTTOM_HOOK_TAIL_MM,(0.18,0.54,0.72))
            for j,y in enumerate(ypos,1):
                name=f'{BEAM_ID}-BottomExtra-S{span_i:02d}-{j:02d}'
                mark=f'{BEAM_ID}-EB-S{span_i:02d}-DB{dmm}'
                worldline=[V(v.x(),v.y()+y,v.z()) for v in centerline]
                info=note_rebar(name,'extra_bottom',dmm,length,mark,span_index=span_i,
                    extra={'shape':'GO-EB-90-2Ends',
                           'end_hooks':'90deg-both-ends-up',
                           'tail_straight_after_bend_mm':SPECIAL_BOTTOM_HOOK_TAIL_MM,
                           'bend_radius_centerline_mm':bend_r*1000,
                           'start_m':xa,'end_m':xb},centerline=worldline)
                add(proto,name,'extra_bottom','IfcReinforcingBar',position=(0,y,0),info=info)
                bar_meta[name]=info
                extra_hook_entries.append({'name':name,'kind':'extra_bottom','db_mm':dmm,
                    'points':worldline,'xmin':xa,'xmax':xb})
                bar_geom.append({'name':name,'kind':'extra_bottom','diameter_mm':dmm,
                    'mark':mark,'mesh':proto,'offset':(0,y,0),
                    'span_index':span_i,'support_index':0,'points':worldline})

    # Fail early if special hooked ends collide across top/bottom layouts.
    check_extra_hook_clashes(extra_hook_entries)

    # ONE reusable stirrup prototype across all spans.
    for span_i,(x0,x1) in enumerate(zip(x_support[:-1],x_support[1:]),1):
        stations=span_stirrups(span_i,x0,x1)
        for j,data in enumerate(stations,1):
            x=data['x']
            name=f'{BEAM_ID}-Tie-S{span_i:02d}-{j:03d}'
            mark=f'{BEAM_ID}-ST-S{span_i:02d}-RB{STIRRUP_DB_MM}-H{STIRRUP_HOOK_DEG}'
            info=note_rebar(name,'stirrup',STIRRUP_DB_MM,tie_length,mark,
                span_index=span_i,extra={'x_m':x,'zones':data['zones'],
                'shape':f'GO-ST{STIRRUP_HOOK_DEG}','hook_straight_extension_mm':STIRRUP_HOOK_TAIL_MM,'tie_zone_rule':get_span_tie_config(span_i)})
            add(tie_proto,name,'stirrup','IfcReinforcingBar',position=(x,0,0),info=info)
            bar_meta[name]=info
            bar_geom.append({'name':name,'kind':'stirrup','diameter_mm':STIRRUP_DB_MM,
                'mark':mark,'mesh':tie_proto,'offset':(x,0,0),
                'span_index':span_i,'support_index':0,
                'points':[V(v.x()+x,v.y(),v.z()) for v in tie_path]})
            stirrup_stations.append({'span':span_i,'x_m':round(x,6),'zones':data['zones'],'support_face_offset_m':get_span_tie_config(span_i)['first_left_m']})

    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

