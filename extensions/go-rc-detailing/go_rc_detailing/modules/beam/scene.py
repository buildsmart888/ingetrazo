"""Source-locked accepted v0.7 beam stages.

No AST, exec, generated-source evaluation, or GUI mutation occurs here.
Each phase accepts an explicit runtime domain and shared build state.
"""
from __future__ import annotations

def assemble(domain, state):
    BEAM_ID = domain.BEAM_ID
    Group = domain.Group
    Mesh = domain.Mesh
    TAG_KEY = domain.TAG_KEY
    items = state.items
    # Group as native IngeTrazo assembly with exactly one top-level scene group.
    categories=[
        ('Concrete','concrete'),('Main Top','top'),('Main Bottom','bottom'),
        ('Extra Top','extra_top'),('Extra Bottom','extra_bottom'),
        ('Stirrups','stirrup'),('Formwork','formwork'),('Supports (reference)','support')]
    parent=Group(Mesh(),name=f'{BEAM_ID}-RC Continuous Beam Assembly')
    kids=[]; used=set()
    for title,kind in categories:
        members=[g for g in items if g.ext[TAG_KEY]['kind']==kind]
        if not members: continue
        subgroup=Group(Mesh(),name=f'{BEAM_ID} | {title}')
        subgroup.adopt(members)
        subgroup.component=False
        subgroup.ext={TAG_KEY:{'beam_id':BEAM_ID,'kind':'category','part_type':kind}}
        kids.append(subgroup)
        used.update(map(id,members))
    if len(used)!=len(items):
        raise ValueError('Native group membership mismatch')
    parent.adopt(kids)
    parent.component=False
    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

def verify_and_publish(domain, state):
    B = domain.B
    BEAM_ID = domain.BEAM_ID
    H = domain.H
    Layer = domain.Layer
    SHOW_MARK_LABELS = domain.SHOW_MARK_LABELS
    SPANS_M = domain.SPANS_M
    SPECIAL_BOTTOM_COUNT = domain.SPECIAL_BOTTOM_COUNT
    SPECIAL_BOTTOM_DB_MM = domain.SPECIAL_BOTTOM_DB_MM
    SPECIAL_TOP_COUNT = domain.SPECIAL_TOP_COUNT
    SPECIAL_TOP_DB_MM = domain.SPECIAL_TOP_DB_MM
    STIRRUP_DB_MM = domain.STIRRUP_DB_MM
    STIRRUP_HOOK_DEG = domain.STIRRUP_HOOK_DEG
    SUPPORT_WIDTH_M = domain.SUPPORT_WIDTH_M
    TAG_KEY = domain.TAG_KEY
    TextLabel = domain.TextLabel
    V = domain.V
    _add_verification_markers = domain._add_verification_markers
    scene = domain.scene
    verify_generated_rebar = domain.verify_generated_rebar
    bar_geom = state.bar_geom
    bar_locations = state.bar_locations
    bar_meta = state.bar_meta
    items = state.items
    kids = state.kids
    parent = state.parent
    stirrup_stations = state.stirrup_stations
    tie_r = state.tie_r
    x_support = state.x_support
    z_extra_bot = state.z_extra_bot
    z_extra_top = state.z_extra_top
    verification=verify_generated_rebar(bar_geom,bar_meta,stirrup_stations,bar_locations,
                                        x_support,tie_r)
    # Optional patched-host display metadata. Does not alter solids or BBS.
    from ...rebar_host_bridge import attach_beam_proxies
    lod_status=attach_beam_proxies(state)
    if lod_status['attached']:
        print('GO RC Rebar LOD: {}/{} signed ({} shared definitions)'.format(
            lod_status['attached'],lod_status['attempted'],lod_status['unique_definitions']))
    if getattr(state, 'dual_display_enabled', False):
        from ...dual_display import register_beam
        stored = register_beam(scene, state, BEAM_ID)
        if stored != len(state.bar_geom):
            raise RuntimeError('Incomplete GO RC Wire centreline registration')
    verification_markers,verification_category=_add_verification_markers(parent,verification['issues'])
    parent.ext={TAG_KEY:{'beam_id':BEAM_ID,'kind':'assembly',
        'spans_m':SPANS_M,'hook_angle_deg':STIRRUP_HOOK_DEG,
        'support_width_m':SUPPORT_WIDTH_M,'support_reference_only':True,
        'parts':len(items),'categories':[k.name for k in kids]}}
    scene.groups.append(parent)
    if getattr(state, 'dual_display_enabled', False):
        from ...dual_display import refresh_wire_overlays
        display_stats = refresh_wire_overlays(scene)
        print('GO RC Dual Display:', display_stats['bars'], 'bars /',
              display_stats['edges'], 'centerline edges')
    if SHOW_MARK_LABELS:
        from core.textlabel import TextLabel
        layer='GO | Bar Marks'
        if not any(ly.name==layer for ly in scene.layers):
            scene.layers.append(Layer(layer))
        for i,(xa,xb) in enumerate(zip(x_support[:-1],x_support[1:]),1):
            xc=(xa+xb)/2
            scene.text_labels.append(TextLabel(
                anchor=V(xc,0,H),offset=V(0,0,0.23),
                text=f'{BEAM_ID} S{i:02d}: {(xb-xa)*1000:.0f} mm / '
                     f'{B*1000:.0f}x{H*1000:.0f}',layer=layer))
            if SPECIAL_BOTTOM_COUNT:
                scene.text_labels.append(TextLabel(
                    anchor=V(xc,0,z_extra_bot),offset=V(0,-0.25,-0.17),
                    text=f'{BEAM_ID}-EB-S{i:02d}-DB{SPECIAL_BOTTOM_DB_MM} '
                         f'{SPECIAL_BOTTOM_COUNT} bars / 90deg UP ends',layer=layer))
            ties_in_span=[d for d in stirrup_stations if d['span']==i]
            if ties_in_span:
                mid_tie=ties_in_span[len(ties_in_span)//2]
                scene.text_labels.append(TextLabel(
                    anchor=V(mid_tie['x_m'],B/2,H/2),offset=V(0,0.30,0.04),
                    text=f'{BEAM_ID}-ST-S{i:02d}-RB{STIRRUP_DB_MM} '
                         f'{len(ties_in_span)} pcs / {STIRRUP_HOOK_DEG}deg',layer=layer))
        if SPECIAL_TOP_COUNT:
            for i,sx in enumerate(x_support,1):
                scene.text_labels.append(TextLabel(
                    anchor=V(sx,0,z_extra_top),offset=V(0,-0.25,0.12),
                    text=f'{BEAM_ID}-ET-P{i:02d}-DB{SPECIAL_TOP_DB_MM} '
                         f'{SPECIAL_TOP_COUNT} bars / 90deg DOWN ends',layer=layer))

    # Retain shared objects/closures and scalar outputs between accepted stages.
    state.__dict__.update({k: v for k, v in locals().items()
                           if k not in ('state', 'domain', 'local_snapshot')})
    return state

