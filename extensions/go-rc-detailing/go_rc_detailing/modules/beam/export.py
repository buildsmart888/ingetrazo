"""Source-locked accepted v0.7 beam stages.

No AST, exec, generated-source evaluation, or GUI mutation occurs here.
Each phase accepts an explicit runtime domain and shared build state.
"""
from __future__ import annotations

def write_outputs(domain, state):
    B = domain.B
    BEAM_ID = domain.BEAM_ID
    COVER = domain.COVER
    H = domain.H
    OUT_BASE = domain.OUT_BASE
    SPANS_M = domain.SPANS_M
    SPECIAL_BOTTOM_HOOK_TAIL_MM = domain.SPECIAL_BOTTOM_HOOK_TAIL_MM
    SPECIAL_HOOK_RADIUS_MULTIPLIER = domain.SPECIAL_HOOK_RADIUS_MULTIPLIER
    SPECIAL_TOP_HOOK_TAIL_MM = domain.SPECIAL_TOP_HOOK_TAIL_MM
    STIRRUP_HOOK_DEG = domain.STIRRUP_HOOK_DEG
    STIRRUP_HOOK_TAIL_MM = domain.STIRRUP_HOOK_TAIL_MM
    SUPPORT_DEPTH_M = domain.SUPPORT_DEPTH_M
    SUPPORT_REFERENCE_HEIGHT_M = domain.SUPPORT_REFERENCE_HEIGHT_M
    SUPPORT_WIDTH_M = domain.SUPPORT_WIDTH_M
    WRITE_IFC = domain.WRITE_IFC
    _build_bbs_verified_rows = domain._build_bbs_verified_rows
    csv = domain.csv
    export_beam_ifc = domain.export_beam_ifc
    get_span_tie_config = domain.get_span_tie_config
    json = domain.json
    X = state.X
    bar_geom = state.bar_geom
    bar_locations = state.bar_locations
    bar_meta = state.bar_meta
    form_meta = state.form_meta
    items = state.items
    kids = state.kids
    parent = state.parent
    span_concrete_m3 = state.span_concrete_m3
    span_mass_by_kind = state.span_mass_by_kind
    stirrup_stations = state.stirrup_stations
    support_references = state.support_references
    tie_bounds = state.tie_bounds
    verification = state.verification
    verification_markers = state.verification_markers
    x_support = state.x_support
    # File outputs, independent from built-in IFC exporter because IngeTrazo
    # v0.5.8 does not descend nested tags and lacks reinforcing-bar QTO.
    out_dir=OUT_BASE/BEAM_ID
    out_dir.mkdir(parents=True,exist_ok=True)
    ifc_path=out_dir/f'{BEAM_ID}_BIM.ifc'
    if WRITE_IFC:
        export_beam_ifc(items,ifc_path,bar_meta,form_meta)

    # Bar schedule by all marks including extra steel + per-span ties.
    by_mark={}
    for name,info in bar_meta.items():
        mark=info['mark']
        s=by_mark.setdefault(mark,{'mark':mark,'kind':info['kind'],
            'db_mm':info['diameter_mm'],'each_length_m':info['length_m'],
            'quantity':0,'shape':info.get('shape','GO-Straight'),'total_mass_kg':0.,
            'hook_deg':info['hook_deg']})
        if abs(s['each_length_m']-info['length_m'])>1e-6:
            raise ValueError(f'Same bar mark {mark} has inconsistent lengths')
        s['quantity']+=1
        s['total_mass_kg']+=info['weight_kg']
    bbs_rows=[]; boq_rows=[]
    for mark,s in sorted(by_mark.items()):
        example=next(v for v in bar_meta.values() if v['mark']==mark)
        bbs_rows.append({'beam':BEAM_ID,'mark':mark,'type':s['kind'],
            'diameter_mm':s['db_mm'],'shape':s['shape'],
            'hook_deg':s['hook_deg'],'end_hooks':example.get('end_hooks','stirrup hook' if s['kind']=='stirrup' else '90deg-both-ends'),
            'hook_straight_tail_after_bend_mm':example.get('tail_straight_after_bend_mm',
                                              example.get('hook_straight_extension_mm','')),
            'bend_radius_centerline_mm':example.get('bend_radius_centerline_mm',''),
            'quantity':s['quantity'],
            'length_each_m':round(s['each_length_m'],6),
            'total_length_m':round(s['each_length_m']*s['quantity'],6),
            'weight_total_kg':round(s['total_mass_kg'],6),
            'approval':'SCHEMATIC - engineering detail check required'})
        boq_rows.append({'beam':BEAM_ID,'category':s['kind'],'mark':mark,
            'unit':'kg','quantity':round(s['total_mass_kg'],6)})
    for i,vol in enumerate(span_concrete_m3,1):
        boq_rows.append({'beam':BEAM_ID,'category':f'concrete span {i}',
            'mark':f'{BEAM_ID}-S{i:02d}','unit':'m3','quantity':round(vol,6)})
    for name,area in form_meta.items():
        boq_rows.append({'beam':BEAM_ID,'category':'formwork contact',
            'mark':name,'unit':'m2','quantity':round(area,6)})
    def csv_write(filename,fields,rows):
        with (out_dir/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields)
            w.writeheader();w.writerows(rows)
    csv_write(f'{BEAM_ID}_BBS.csv',list(bbs_rows[0]) if bbs_rows else [],bbs_rows)
    csv_write(f'{BEAM_ID}_BOQ.csv',['beam','category','mark','unit','quantity'],boq_rows)
    csv_write(f'{BEAM_ID}_StirrupStations.csv',['span','x_m','zones','from_left_face_m','from_right_face_m'],[
        {'span':d['span'],'x_m':d['x_m'],'zones':' + '.join(d['zones']),
         'from_left_face_m':round(d['x_m']-(x_support[d['span']-1]+SUPPORT_WIDTH_M/2),6),
         'from_right_face_m':round((x_support[d['span']]-SUPPORT_WIDTH_M/2)-d['x_m'],6)}
        for d in stirrup_stations])
    item_fields=['beam','part','mark','type','dia_mm','span_index','support_index',
                 'end_hooks','straight_tail_after_bend_mm','bend_radius_centerline_mm',
                 'start_x_m','end_x_m','cut_length_m','theoretical_mass_kg',
                 'allocation_weight_kg_by_span','status']
    item_rows=[]
    for name,info in sorted(bar_meta.items()):
        item_rows.append({'beam':BEAM_ID,'part':name,'mark':info['mark'],
            'type':info['kind'],'dia_mm':info['diameter_mm'],
            'span_index':info.get('span_index',0),'support_index':info.get('support_index',0),
            'end_hooks':info.get('end_hooks',f"stirrup {STIRRUP_HOOK_DEG}deg" if info['kind']=='stirrup' else ''),
            'straight_tail_after_bend_mm':info.get('tail_straight_after_bend_mm',
                 info.get('hook_straight_extension_mm','')),
            'bend_radius_centerline_mm':info.get('bend_radius_centerline_mm',''),
            'start_x_m':info.get('start_m',''),'end_x_m':info.get('end_m',''),
            'cut_length_m':round(info['length_m'],6),
            'theoretical_mass_kg':round(info['weight_kg'],6),
            'allocation_weight_kg_by_span':json.dumps(info['allocation_weight_kg_by_span']),
            'status':'SCHEMATIC geometry - not an approved fabrication BBS'})
    csv_write(f'{BEAM_ID}_BBS_Items.csv',item_fields,item_rows)
    bbs_verification_rows=_build_bbs_verified_rows(bar_geom,bar_meta)
    if bbs_verification_rows:
        csv_write(f'{BEAM_ID}_BBS_DetailVerification.csv',list(bbs_verification_rows[0]),bbs_verification_rows)
    issues_csv_rows=[]
    for entry in verification['issues']:
        issues_csv_rows.append({'id':entry['id'],'severity':entry['severity'],
             'rule':entry['rule'],'parts':' | '.join(entry['parts']),
             'x_mm':entry['xyz_m'][0]*1000,'y_mm':entry['xyz_m'][1]*1000,
             'z_mm':entry['xyz_m'][2]*1000,'measured_mm':entry['measured_mm'],
             'required_mm':entry['required_mm'],'message':entry['message'],
             'method':entry['method']})
    csv_write(f'{BEAM_ID}_Verification_Issues.csv',
             ['id','severity','rule','parts','x_mm','y_mm','z_mm','measured_mm','required_mm','message','method'],
             issues_csv_rows)
    (out_dir/f'{BEAM_ID}_Verification.json').write_text(
        json.dumps(verification,indent=2,ensure_ascii=False),encoding='utf-8')
    span_fields=['beam','span','start_center_m','end_center_m','clear_length_m',
                 'category','unit','quantity','measurement']
    span_boq=[]
    for i,(xa,xb) in enumerate(zip(x_support[:-1],x_support[1:]),1):
        area=(xb-xa)*(B+2*H)
        span_boq.append({'beam':BEAM_ID,'span':i,'start_center_m':xa,'end_center_m':xb,
            'clear_length_m':xb-xa-SUPPORT_WIDTH_M,'category':'concrete (gross)',
            'unit':'m3','quantity':round(span_concrete_m3[i-1],6),'measurement':'centre-to-centre gross volume'})
        span_boq.append({'beam':BEAM_ID,'span':i,'start_center_m':xa,'end_center_m':xb,
            'clear_length_m':xb-xa-SUPPORT_WIDTH_M,'category':'formwork contact (gross)',
            'unit':'m2','quantity':round(area,6),'measurement':'3-face contact excluding column interruption'})
        for kind,mass in sorted(span_mass_by_kind[i-1].items()):
            span_boq.append({'beam':BEAM_ID,'span':i,'start_center_m':xa,'end_center_m':xb,
                'clear_length_m':xb-xa-SUPPORT_WIDTH_M,'category':kind,
                'unit':'kg','quantity':round(mass,6),
                'measurement':'theoretical bar centreline length allocated at support centre-lines'})
    csv_write(f'{BEAM_ID}_BOQ_by_Span.csv',span_fields,span_boq)

    total_mass=sum(i['weight_kg'] for i in bar_meta.values())
    report={'id':BEAM_ID,'version':'0.7.0','spans_m':SPANS_M,
        'supports_x_m':x_support,'total_length_m':X,
        'support_reference_only':True,
        'support_reference_width_m':SUPPORT_WIDTH_M,
        'support_reference_depth_m':SUPPORT_DEPTH_M,
        'support_reference_height_m':SUPPORT_REFERENCE_HEIGHT_M,
        'support_reference_markers':support_references,
        'stirrup_zone_configuration_by_span':{str(i):get_span_tie_config(i) for i in range(1,len(SPANS_M)+1)},
        'special_top_end_hook':{'angle_deg':90,'direction':'down','both_ends':True,
                  'straight_tail_after_bend_mm':SPECIAL_TOP_HOOK_TAIL_MM},
        'special_bottom_end_hook':{'angle_deg':90,'direction':'up','both_ends':True,
                  'straight_tail_after_bend_mm':SPECIAL_BOTTOM_HOOK_TAIL_MM},
        'special_hook_bend_radius_multiplier':SPECIAL_HOOK_RADIUS_MULTIPLIER,
        'quantity_allocation_mass_by_span_kg':span_mass_by_kind,
        'cross_section_m':{'width':B,'depth':H},'cover_m':COVER,
        'stirrup_hook_deg':STIRRUP_HOOK_DEG,
        'hook_return_corner':'upper_left',
        'stirrup_hook_straight_extension_mm':STIRRUP_HOOK_TAIL_MM,
        'tie_mesh_bounds_m':{'x':tie_bounds[0],'y':tie_bounds[1],'z':tie_bounds[2]},
        'stirrup_stations':stirrup_stations,
        'longitudinal_bar_positions_and_tie_clearance':bar_locations,
        'special_bar_placement':'separate inner symmetric row; MAIN corner positions are unchanged',
        'gross_concrete_m3':sum(span_concrete_m3),
        'formwork_contact_m2':sum(form_meta.values()),
        'steel_total_kg':total_mass,'main_and_extra_marks':bbs_rows,'bar_schedule_items':item_rows,
        'model_part_count':len(items),
        'native_parent_group':parent.name,
        'nested_category_count':len(kids),
        'shared_mesh_prototypes':len({id(g.mesh) for g in items}),
        'verification':{'status':verification['status'],'counts':verification['counts'],
            'report_filename':f'{BEAM_ID}_Verification.json',
            'issue_csv':f'{BEAM_ID}_Verification_Issues.csv',
            'BBS_detail_filename':f'{BEAM_ID}_BBS_DetailVerification.csv',
            'markers_added':len(verification_markers),
            'not_checked':verification['not_checked']},
        'warnings':[
            'NOT a construction-ready structural detail or validated bar bending schedule.',
            'Upper-left returns use sin/cos hook tangency and a small OUT-OF-PLANE 3D stagger to avoid colliding render meshes; do not use as a fabrication-ready planar shape. Verify true cut/bend plan, bend pin and code with a structural engineer.',
            'Support positions are centre-lines, not actual column widths or faces.',
            'Main bars are continuous even across spans; lapping / stock length / development not designed.',
            'Special top/bottom bars have 90 degree hooks DOWN/UP at BOTH ends; radius and straight tails are model inputs, NOT verified development anchorage.',
            'Support reference solids are visual-only and excluded from IFC/BOQ; real column/joint geometry and tie confinement are not designed.',
            'Per-span tie station offsets are measured from assumed column faces, not confirmed column faces.',
            'Main+extra bars use theoretical idealized swept centreline lengths, not approved cut lengths or bend deductions.',
            '3D rebar collision screening uses sampled capsule centreline; mesh-triangle exact collision is not performed.',
            'Concrete volumes are gross, formwork areas are contact areas, rebar theoretical kg.',
            'Native IFC exporter in IngeTrazo 0.5.8 does not export nested child IFC tags; use the generated IFC.',
            'Static labels do not follow moved assembly.'
        ]}
    (out_dir/f'{BEAM_ID}_Metadata.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

def finish(domain, state):
    BEAM_ID = domain.BEAM_ID
    SPANS_M = domain.SPANS_M
    SPECIAL_BOTTOM_COUNT = domain.SPECIAL_BOTTOM_COUNT
    SPECIAL_BOTTOM_HOOK_TAIL_MM = domain.SPECIAL_BOTTOM_HOOK_TAIL_MM
    SPECIAL_TOP_COUNT = domain.SPECIAL_TOP_COUNT
    SPECIAL_TOP_HOOK_TAIL_MM = domain.SPECIAL_TOP_HOOK_TAIL_MM
    STIRRUP_HOOK_DEG = domain.STIRRUP_HOOK_DEG
    STIRRUP_HOOK_TAIL_MM = domain.STIRRUP_HOOK_TAIL_MM
    VERIFY_SHOW_REPORT = domain.VERIFY_SHOW_REPORT
    math = domain.math
    show_go_rebar_verification_report = domain.show_go_rebar_verification_report
    stirrup_shape_vertices = domain.stirrup_shape_vertices
    tie_parameters = domain.tie_parameters
    X = state.X
    bar_locations = state.bar_locations
    bar_meta = state.bar_meta
    form_meta = state.form_meta
    items = state.items
    out_dir = state.out_dir
    parent = state.parent
    span_concrete_m3 = state.span_concrete_m3
    stirrup_stations = state.stirrup_stations
    tie_r = state.tie_r
    total_mass = state.total_mass
    verification = state.verification
    x = state.x
    x_support = state.x_support
    y = state.y
    print('GO RC Beam v0.7.0: Model generated')
    print(f'{BEAM_ID}: {len(SPANS_M)} spans / {X:.3f} m; native parent: {parent.name}')
    print(f'Concrete: {sum(span_concrete_m3):.3f} m3 | Formwork: {sum(form_meta.values()):.3f} m2')
    print(f'Rebar: {len(bar_meta)} individual pieces | {total_mass:.3f} kg')
    print(f'Stirrups: {len(stirrup_stations)} pieces | {STIRRUP_HOOK_DEG}deg hooks')
    print(f'Supports: {len(x_support)} at '+', '.join(f'{x:.3f}m' for x in x_support))
    print('Special TOP: 90deg DOWN, BOTH ends | straight tail {} mm'.format(SPECIAL_TOP_HOOK_TAIL_MM) if SPECIAL_TOP_COUNT else 'Special TOP: disabled')
    print('Special BOTTOM: 90deg UP, BOTH ends | straight tail {} mm'.format(SPECIAL_BOTTOM_HOOK_TAIL_MM) if SPECIAL_BOTTOM_COUNT else 'Special BOTTOM: disabled')
    print('BBS items and BOQ by span:', out_dir)
    print('Tie-to-top-bar 2D clearance (mm):',
          f"{bar_locations['top']['minimum_tie_clearance_mm']:.2f}")
    print('Note: above is a 2D projection; use 3D capsule issue report for actual clashes.')
    print('Hook straight tail AFTER bend (mm):',STIRRUP_HOOK_TAIL_MM)
    if STIRRUP_HOOK_DEG==90:
        print('90 deg returns: A DOWN left / B RIGHT along top; both at upper-left corner')
        print('90 deg tangent setback R (mm): {:.1f}'.format(tie_r*1000))
    if STIRRUP_HOOK_DEG==135:
        print('135 deg returns: B raised to TOP-LEFT TANGENCY; separated 3D hooks')
        print('B hook 135: R={:.1f} mm; t=R*tan(67.5deg)={:.2f} mm'.format(tie_r*1000,tie_r*math.tan(math.radians(67.5))*1000))
        print('B vertical tangent Z={:.1f} mm; B virtual vertex Z={:.1f} mm; B tip Z={:.1f} mm'.format(
            (tie_parameters()[3]-tie_r)*1000,
            (tie_parameters()[3]-tie_r+tie_r*math.tan(math.radians(67.5)))*1000,
            stirrup_shape_vertices()[0][-1].z()*1000))
    print('Top main Y stations (mm):',
          ', '.join(f'{y*1000:.1f}' for y in bar_locations['top']['y_m']))
    print(f'Shared GPU mesh prototypes: {len({id(g.mesh) for g in items})}; parent: ONE top-level group')
    print('Output:',out_dir)
    print('GO RC Beam v0.7 verification:',verification['status'],
          f"{verification['counts']['ERROR']} errors / {verification['counts']['WARNING']} warnings")
    print('Issue locations: GO | Verification Markers; report CSV/JSON:',out_dir)
    print('NOT CHECKED: design-code compliance, lapping, anchorage, bend tooling, exact mesh collision')
    if VERIFY_SHOW_REPORT:
        # Open the modal after the Python Console SnapshotImport completes,
        # otherwise Locate/Zoom would run while the scene is mid-mutation.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda result=verification: show_go_rebar_verification_report(result))
    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

