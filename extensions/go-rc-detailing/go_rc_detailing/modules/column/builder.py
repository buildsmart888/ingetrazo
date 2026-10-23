"""Native group & geometry composition for RC columns."""
from __future__ import annotations
import math
from pathlib import Path
from ...beam_adapter import _static_domain
from ...rebar_host_bridge import attach_local_centerline
from ...adapters.ingetrazo import bim as bim_adapter
from ...adapters.ingetrazo import mesh as mesh_adapter
from .params import ColumnParams, check_params
from .geometry import (_box, _cylinder, _cylinder_shell, _spiral_rebar, _hooked_main_bar,
    _rect_main_positions, _circle_main_positions, _min_clearance_xy, _validate_main_hooks,
    _tie_positions, _kgpm)
from .export import finalize_column, ColumnBuildData

def _step(progress, value, label):
    if progress is not None:
        progress.report(value, label)


def create_column(p: ColumnParams, scope, out_base=None, progress=None,
                  dual_display=False):
    """Build inside an IngeTrazo SnapshotImport transaction. Returns metadata."""
    check_params(p)
    _step(progress, 8, "ตรวจพารามิเตอร์ / Validate column input")
    scene=scope["scene"]
    Mesh=scope["Mesh"]
    Group=scope["Group"]
    bim=scope["bim"]
    from core.layers import Layer
    from PySide6.QtGui import QMatrix4x4
    from ...adapters.ingetrazo.mesh import assert_watertight
    from ...adapters.ingetrazo.scene import assert_unique_column_id
    assert_unique_column_id(scene,p.column_id)
    _step(progress, 16, "เตรียมเรขาคณิต / Prepare geometry")
    # This is an ordinary imported module: no source slicing, AST or exec.
    # Reuse the accepted hook math through the statically split Phase2 domain.
    eng=_static_domain(scope).__dict__
    w=p.width_mm/1000
    dep=p.depth_mm/1000
    h=p.height_mm/1000
    diameter=p.diameter_mm/1000
    cover=p.cover_mm/1000
    dt=p.tie_db_mm/1000
    db=p.longitudinal_db_mm/1000
    eng.update({"B":w,"H":dep,"COVER":cover,"STIRRUP_DB_MM":p.tie_db_mm,
                "STIRRUP_HOOK_DEG":p.tie_hook_deg,"STIRRUP_HOOK_TAIL_MM":p.tie_hook_tail_mm,
                "FIRST_LEFT_M":max(.05,cover+dt+0.003),
                "FIRST_RIGHT_M":max(.05,cover+dt+0.003)})
    blue=(0.26,0.42,0.80);yellow=(0.85,0.72,0.27)
    gray=(0.67,0.70,0.73);plywood=(0.60,0.44,0.29)
    parent=Group(Mesh(),name=p.column_id+"-RC "+("Rectangular" if p.shape=="rect" else "Circular")+" Column Assembly")
    children={name:[] for name in ("Concrete","Main Rebar","Ties / Hoops","Formwork")}
    bars={}
    lod_cache={}  # one signed metadata definition per shared Mesh + centreline
    if dual_display:
        from ...dual_display import register_bar
    form_areas={}
    boq=[]
    def add(mesh,name,kind,cls,place=None,meta=None):
        g=Group(mesh,name=name)
        g.layer="GO RC | "+kind
        if place is not None:
            g.xform=QMatrix4x4()
            g.xform.translate(*place)
        if cls:
            bim_adapter.tag_group(g,cls,name,bim)
        g.ext={"go_rc_column":dict(column_id=p.column_id,shape=p.shape,category=kind,**(meta or {}))}
        children[kind].append(g)
        return g

    if p.shape=="rect":
        concrete=_box(eng,-w/2,-dep/2,0,w/2,dep/2,h,color=gray,opacity=.38)
        volume=w*dep*h
        positions=_rect_main_positions(p)
        # Rotate the EXACT accepted beam XY-projected 90/135 hook centreline
        # into a horizontal (XY) COLUMN tie. No change to beam hook math.
        beam_path,bend_radius,_=eng["stirrup_shape_vertices"]()
        V=eng["V"]
        path=[V(v.y(),v.z()-dep/2,v.x()) for v in beam_path]
        path_fillet=eng["_fillet_polyline"](path,bend_radius,10)
        _step(progress, 22, "สร้างเหล็กปลอกสี่เหลี่ยม / Sweeping rectangular tie")
        tie,_tie_len=eng["make_rebar_mesh"](path,dt,bend_radius,yellow,closed=False)
        tie_length=_tie_len
        # Centreline+bar radius must remain within the specified concrete cover.
        allowance=0.0012
        if any(abs(pt.x())+dt/2 > w/2-cover+allowance or
               abs(pt.y())+dt/2 > dep/2-cover+allowance for pt in path_fillet):
            raise ValueError("Rectangular tie geometry escapes concrete cover")
        form_defs=[("Side-X-",(-w/2-p.plywood_mm/1000,-dep/2,0,-w/2,dep/2,h),dep*h),
                   ("Side-X+",(w/2,-dep/2,0,w/2+p.plywood_mm/1000,dep/2,h),dep*h),
                   ("Side-Y-",(-w/2,-dep/2-p.plywood_mm/1000,0,w/2,-dep/2,h),w*h),
                   ("Side-Y+",(-w/2,dep/2,0,w/2,dep/2+p.plywood_mm/1000,h),w*h)]
    else:
        volume=math.pi*diameter*diameter*h/4
        concrete=_cylinder(eng,diameter/2,h,gray,.38)
        positions=_circle_main_positions(p)
        _step(progress, 22, "สร้างเหล็กปลอกเกลียว / Sweeping continuous spiral")
        tie,tie_length,spiral_info=_spiral_rebar(eng,p)
        path_fillet=[]
        form_defs=[("Circular-Mantle",None,math.pi*diameter*h)]

    _step(progress, 28, "สร้าง Solid คอนกรีต / Concrete solid")
    add(concrete,p.column_id+"-Concrete","Concrete","IfcColumn",
        meta={"gross_volume_m3":volume})
    # Strictly geometric screen: top-to-bottom clear spacing, nominal cover.
    min_clear=_min_clearance_xy(positions,db)
    if min_clear<0.025-1e-8:
        raise ValueError("Longitudinal bar clear spacing under 25 mm geometry input")
    _validate_main_hooks(p,positions)
    _step(progress, 35, "สร้างต้นแบบเหล็กยืนงอปลาย / Sweeping main-bar prototype")
    bar_proto,bar_length,bar_path,bar_radius=_hooked_main_bar(eng,p)
    assert_watertight(bar_proto,p.column_id+"-Main")
    # The tube uses a filleted path; bar_path itself is the unfilleted control
    # polygon. Preserve the actual swept centreline for interactive LOD.
    main_lod_path=eng["_fillet_polyline"](bar_path,bar_radius,10) if bar_radius>0 else bar_path
    _step(progress, 40, "สร้างเหล็กยืน / Main reinforcement")
    for i,(x,y) in enumerate(positions,1):
        name=f"{p.column_id}-Main-{i:02d}"
        data=dict(kind="main",diameter_mm=p.longitudinal_db_mm,length_m=bar_length,
                  weight_kg=_kgpm(p.longitudinal_db_mm)*bar_length,
                  hook_top=p.main_hook_top,hook_bottom=p.main_hook_bottom,
                  hook_top_direction=p.main_hook_top_direction if p.main_hook_top else "none",
                  hook_bottom_direction=p.main_hook_bottom_direction if p.main_hook_bottom else "none",
                  hook_top_tail_mm=p.main_hook_top_tail_mm if p.main_hook_top else 0,
                  hook_bottom_tail_mm=p.main_hook_bottom_tail_mm if p.main_hook_bottom else 0,
                  top_projection_mm=p.main_top_projection_mm,
                  bottom_projection_mm=p.main_bottom_projection_mm,
                  z_min_local_m=min(pt.z() for pt in bar_path),
                  z_max_local_m=max(pt.z() for pt in bar_path),
                  bar_shape="GO-C-M90" if (p.main_hook_top or p.main_hook_bottom) else "straight",
                  mark=f"{p.column_id}-M-DB{p.longitudinal_db_mm:g}"+
                       (("-"+("T" if p.main_hook_top else "")+
                         ("B" if p.main_hook_bottom else ""))
                        + "-" + ("O" if p.main_hook_top_direction == "outward" else "I")
                        + ("O" if p.main_hook_bottom_direction == "outward" else "I")
                        if (p.main_hook_top or p.main_hook_bottom) else ""))
        # Rotate each main bar by its radial position. +X is outward,
        # -X inward; the same prototype works for every bar.
        g=add(bar_proto,name,"Main Rebar","IfcReinforcingBar",meta=data)
        g.xform=QMatrix4x4()
        g.xform.translate(x,y,0)
        g.xform.rotate(math.degrees(math.atan2(y,x)),0,0,1)
        attach_local_centerline(g,main_lod_path,p.longitudinal_db_mm,lod_cache)
        if dual_display:
            register_bar(scene,g,main_lod_path,assembly_id=p.column_id,
                         diameter_mm=p.longitudinal_db_mm)
        bars[name]=data
        if progress is not None and (i % 4 == 0 or i == len(positions)):
            progress.report(40 + round(17*i/len(positions)),
                f"จัดวางเหล็กยืน {i}/{len(positions)} / Place rebar")
    _step(progress, 60, "สร้างปลอกและเกลียว / Ties and spiral")
    assert_watertight(tie,p.column_id+("-Spiral" if p.shape=="circular" else "-Tie"))
    if p.shape=="rect":
        tie_stations=_tie_positions(p)
        tie_mesh_zrad=dt/2 + (dt/2+0.0006)
        for i,z in enumerate(tie_stations,1):
            if z-tie_mesh_zrad<cover-0.001 or z+tie_mesh_zrad>h-cover+0.001:
                raise ValueError("Tie exceeds axial cover; increase first_tie_mm")
            name=f"{p.column_id}-Tie-{i:03d}"
            data=dict(kind="stirrup",diameter_mm=p.tie_db_mm,length_m=tie_length,
                      weight_kg=_kgpm(p.tie_db_mm)*tie_length,
                      mark=f"{p.column_id}-T-RB{p.tie_db_mm:g}-H{p.tie_hook_deg}",
                      z_m=z,hook_deg=p.tie_hook_deg,bar_shape="rectangular_tie")
            tie_group=add(tie,name,"Ties / Hoops","IfcReinforcingBar",place=(0,0,z),meta=data)
            attach_local_centerline(tie_group,path_fillet,p.tie_db_mm,lod_cache)
            if dual_display:
                register_bar(scene,tie_group,path_fillet,assembly_id=p.column_id,
                             diameter_mm=p.tie_db_mm)
            bars[name]=data
    else:
        # One helical solid from bottom to top; pitch is measured axially.
        tie_stations=[]
        name=f"{p.column_id}-Spiral-001"
        data=dict(kind="spiral",diameter_mm=p.tie_db_mm,length_m=tie_length,
                  weight_kg=_kgpm(p.tie_db_mm)*tie_length,
                  mark=f"{p.column_id}-SP-RB{p.tie_db_mm:g}",
                  bar_shape="continuous_helix",spiral_turns=spiral_info["turns"],
                  actual_pitch_mm=spiral_info["pitch_actual_mm"])
        spiral_group=add(tie,name,"Ties / Hoops","IfcReinforcingBar",meta=data)
        # The continuous spiral mesh is locally positioned. An identity
        # transform exposes it as an eligible placement (without moving it).
        spiral_group.xform=QMatrix4x4()
        n=int(spiral_info["segments"])
        turns=int(spiral_info["turns"])
        rr=float(spiral_info["radius_centerline_m"])
        zstart=float(spiral_info["z_start_m"])
        rise=float(spiral_info["z_end_m"])-zstart
        helix_path=[(rr*math.cos(2*math.pi*turns*i/n),
                     rr*math.sin(2*math.pi*turns*i/n),
                     zstart+rise*i/n) for i in range(n+1)]
        attach_local_centerline(spiral_group,helix_path,p.tie_db_mm,lod_cache)
        if dual_display:
            register_bar(scene,spiral_group,helix_path,assembly_id=p.column_id,
                         diameter_mm=p.tie_db_mm)
        bars[name]=data
    _step(progress, 72, "สร้างไม้แบบ / Formwork")
    for part,box,contact in form_defs:
        name=f"{p.column_id}-Form-{part}"
        if not p.show_formwork:
            # Quantity still counts formwork contact, but no geometry is
            # drawn/exported if disabled. Describe omission in metadata.
            continue
        if p.shape=="rect":
            mesh=_box(eng,*box,color=plywood,opacity=.16)
        else:
            mesh=_cylinder_shell(eng,diameter/2,diameter/2+p.plywood_mm/1000,h,plywood,.16)
        add(mesh,name,"Formwork","IfcBuildingElementProxy",
            meta={"contact_area_m2":contact})
        form_areas[name]=contact

    _step(progress, 80, "จัดกลุ่มและ BIM Tag / Group and tag")
    categories=[]
    for cat, members in children.items():
        if not members:continue
        if not any(layer.name=="GO RC | "+cat for layer in scene.layers):
            scene.layers.append(Layer("GO RC | "+cat))
        sub=Group(Mesh(),name=f"{p.column_id} | {cat}")
        sub.adopt(members)
        sub.component=False
        categories.append(sub)
    parent.adopt(categories)
    parent.component=False
    parent.xform=QMatrix4x4()
    parent.xform.translate(p.pos_x_mm/1000,p.pos_y_mm/1000,p.pos_z_mm/1000)
    parent.ext={"go_rc_column":{
        "column_id":p.column_id,"kind":"assembly","shape":p.shape,
        "height_mm":p.height_mm,"bar_count":len(positions),"tie_count":len(tie_stations),
        "main_top_projection_mm":p.main_top_projection_mm,
        "main_bottom_projection_mm":p.main_bottom_projection_mm}}

    if dual_display:
        # Build the wire overlay before ANY external BBS/IFC files are written.
        # Parent's placement matrix maps every local bar path to world space.
        from ...dual_display import refresh_wire_overlays
        display_stats = refresh_wire_overlays(scene, extra_sources=[parent])
        if display_stats['bars'] < len(bars):
            raise RuntimeError('Incomplete column Wire overlay registration')
        print('GO RC Dual Display:',display_stats['bars'], 'bars /',
              display_stats['edges'], 'centerline edges')

    ctx = ColumnBuildData(
        params=p, scene=scene, parent=parent, categories=categories, children=children,
        bars=bars, form_areas=form_areas, positions=positions, tie_stations=tie_stations,
        spiral_info=spiral_info if p.shape == "circular" else None,
        w=w, depth=dep, h=h, diameter=diameter, volume=volume, min_clear=min_clear,
        form_defs=form_defs, engine=eng, out_base=out_base,
    )
    return finalize_column(ctx, progress=progress)

