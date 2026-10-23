"""Native IFC/BOQ/BBS output and single publication point for columns."""
from __future__ import annotations
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from ...adapters.ingetrazo import scene as scene_adapter
from ...adapters.ingetrazo import ifc as ifc_adapter
from .geometry import _kgpm

VERSION = "0.10.3"

@dataclass
class ColumnBuildData:
    params: Any
    scene: Any
    parent: Any
    categories: list
    children: dict
    bars: dict
    form_areas: dict
    positions: list
    tie_stations: list
    spiral_info: dict | None
    w: float
    depth: float
    h: float
    diameter: float
    volume: float
    min_clear: float
    form_defs: list
    engine: dict
    out_base: Any = None


def finalize_column(ctx: ColumnBuildData, progress=None):
    p = ctx.params
    scene, parent, categories, children = ctx.scene, ctx.parent, ctx.categories, ctx.children
    bars, form_areas = ctx.bars, ctx.form_areas
    positions, tie_stations, spiral_info = ctx.positions, ctx.tie_stations, ctx.spiral_info
    w, dep, h, diameter = ctx.w, ctx.depth, ctx.h, ctx.diameter
    volume, min_clear, form_defs, eng = ctx.volume, ctx.min_clear, ctx.form_defs, ctx.engine
    out_base = ctx.out_base
    def step(value, label):
        if progress is not None: progress.report(value, label)

    steel_main_mass=sum(v["weight_kg"] for v in bars.values() if v["kind"]=="main")
    steel_tie_mass=sum(v["weight_kg"] for v in bars.values() if v["kind"] in ("stirrup","spiral"))
    formwork_contact=(2*(w+dep)*h if p.shape=="rect" else math.pi*diameter*h)
    total_steel=steel_main_mass+steel_tie_mass
    # Reports and IFC create external files and should not be interrupted
    # mid-write; cancellation remains available through geometry staging.
    if progress is not None and hasattr(progress, "commit"):
        progress.commit()
    step(84, "ส่งออก IFC4 / Native BIM")
    out_base=Path(out_base) if out_base is not None else Path.home()/"GO_Engineering"/"RC_Column_v0101"
    out_dir=out_base/p.column_id
    out_dir.mkdir(parents=True,exist_ok=True)
    def write_csv(filename,fields,rows):
        with (out_dir/filename).open("w",encoding="utf-8-sig",newline="") as file:
            writer=csv.DictWriter(file,fieldnames=fields)
            writer.writeheader();writer.writerows(rows)

    # Export before publishing the parent to the scene; prevent partially
    # drawn assemblies if the IFC exporter reports a meaningful error.
    if p.export_ifc:
        ifc_adapter.export_column(parent,out_dir/(p.column_id+"_BIM.ifc"),bars,form_areas,p.column_id)
    step(90, "คำนวณ BBS/BOQ / Quantity reports")
    grouped={}
    for info in bars.values():
        a=grouped.setdefault(info["mark"],{
            "column":p.column_id,"mark":info["mark"],"kind":info["kind"],
            "dia_mm":info["diameter_mm"],"quantity":0,
            "shape_code":("GO-C-SPIRAL" if info["kind"]=="spiral" else
                           "GO-C-T"+str(p.tie_hook_deg) if info["kind"]=="stirrup" else
                           ("GO-C-M90-" + ("T" + ("O" if p.main_hook_top_direction == "outward" else "I") if p.main_hook_top else "") + ("B" + ("O" if p.main_hook_bottom_direction == "outward" else "I") if p.main_hook_bottom else ""))
                           if (p.main_hook_bottom or p.main_hook_top) else
                           "GO-C-STRAIGHT"),
            "bend_radius_mm":3*p.tie_db_mm if info["kind"]=="stirrup" else
                             (4*p.longitudinal_db_mm if info["kind"]=="main" and
                              (p.main_hook_bottom or p.main_hook_top) else 0),
            "length_each_m":info["length_m"],"total_length_m":0.0,"weight_kg":0.0,
            "main_top_hook_tail_mm":p.main_hook_top_tail_mm if p.main_hook_top and info["kind"]=="main" else 0,
            "main_bottom_hook_tail_mm":p.main_hook_bottom_tail_mm if p.main_hook_bottom and info["kind"]=="main" else 0,
            "main_top_projection_mm":p.main_top_projection_mm if info["kind"]=="main" else 0,
            "main_bottom_projection_mm":p.main_bottom_projection_mm if info["kind"]=="main" else 0,
            "main_top_hook_direction":info.get("hook_top_direction","none") if info["kind"]=="main" else "none",
            "main_bottom_hook_direction":info.get("hook_bottom_direction","none") if info["kind"]=="main" else "none",
            "spiral_turns":spiral_info["turns"] if p.shape=="circular" and info["kind"]=="spiral" else 0,
            "spiral_pitch_mm":round(spiral_info["pitch_actual_mm"],6) if p.shape=="circular" and info["kind"]=="spiral" else 0})
        a["quantity"]+=1
        a["total_length_m"]+=info["length_m"]
        a["weight_kg"]+=info["weight_kg"]
    bbs=list(grouped.values())
    for item in bbs:
        for key in ("length_each_m","total_length_m","weight_kg"):
            item[key]=round(item[key],6)
    write_csv(p.column_id+"_BBS.csv",
              ["column","mark","kind","dia_mm","quantity","shape_code","bend_radius_mm",
               "length_each_m","total_length_m","weight_kg",
               "main_top_hook_tail_mm","main_bottom_hook_tail_mm",
               "main_top_projection_mm","main_bottom_projection_mm",
               "main_top_hook_direction","main_bottom_hook_direction",
               "spiral_turns","spiral_pitch_mm"],bbs)
    boq=[
        {"column":p.column_id,"category":"Concrete Gross","unit":"m3","quantity":round(volume,6)},
        {"column":p.column_id,"category":"Main Reinforcement","unit":"kg","quantity":round(steel_main_mass,6)},
        {"column":p.column_id,"category":"Ties / Hoops","unit":"kg","quantity":round(steel_tie_mass,6)},
        {"column":p.column_id,"category":"Formwork Contact (theoretical)","unit":"m2","quantity":round(formwork_contact,6)},
    ]
    write_csv(p.column_id+"_BOQ.csv",["column","category","unit","quantity"],boq)
    write_csv(p.column_id+"_TieStations.csv",["column","index","z_m"],
              [{"column":p.column_id,"index":i,"z_m":round(z,6)}
               for i,z in enumerate(tie_stations,1)] if p.shape=="rect" else
              [{"column":p.column_id,"index":1,"z_m":round(spiral_info["z_start_m"],6)},
               {"column":p.column_id,"index":2,"z_m":round(spiral_info["z_end_m"],6)}])
    metadata={
        "version":VERSION,"id":p.column_id,"shape":p.shape,"inputs":asdict(p),
        "concrete_gross_m3":volume,"formwork_contact_m2":formwork_contact,
        "main_bar_count":len(positions),
        "tie_count":len(tie_stations) if p.shape=="rect" else 1,
        "spiral_turns":spiral_info["turns"] if p.shape=="circular" else 0,
        "spiral_pitch_actual_mm":spiral_info["pitch_actual_mm"] if p.shape=="circular" else None,
        "steel_main_kg":steel_main_mass,"steel_ties_kg":steel_tie_mass,
        "steel_total_kg":total_steel,"minimum_longitudinal_xy_clear_mm":min_clear*1000,
        "tie_spacing_actual_max_mm":max((b-a)*1000 for a,b in zip(tie_stations,tie_stations[1:]))
                          if p.shape=="rect" else spiral_info["pitch_actual_mm"],
        "parent_group":parent.name,"category_groups":[x.name for x in categories],
        "mesh_prototypes":len({id(g.mesh) for group in children.values() for g in group}),
        # Domain-level attachment slots for future slab/footing/wall modules;
        # references remain None until a receiving host element is modelled.
        "connection_interfaces":{
            "top":{"face_z_global_mm":p.pos_z_mm+p.height_mm,
                   "straight_projection_mm":p.main_top_projection_mm,
                   "hook":p.main_hook_top,
                   "hook_direction":p.main_hook_top_direction if p.main_hook_top else "none",
                   "host_element_id":None},
            "bottom":{"face_z_global_mm":p.pos_z_mm,
                      "straight_projection_mm":p.main_bottom_projection_mm,
                      "hook":p.main_hook_bottom,
                      "hook_direction":p.main_hook_bottom_direction if p.main_hook_bottom else "none",
                      "host_element_id":None}},
        "not_checked":["engineering code compliance","beam-column joint", "column bar development/lapping",
          "seismic confinement", "mandrel and shop bend rules", "fabrication BBS",
          "exact triangle mesh clashes", "spiral anchorage and confinement code compliance"],
        "geometry_notes":[
          "Rectangular 90/135 hooks are transformed from the LOCKED v0.7 beam geometry",
          "Circular columns use ONE continuous helical spiral, not individual hoop rings",
          "Longitudinal 90-degree top/bottom hooks support independent inward/outward radial directions",
          "OUTWARD hooks intentionally project beyond the column concrete outline into an UNMODELLED footing/joint/slab; host-cover, anchorage, containment and clash NOT checked",
          "Main bars MAY project beyond column faces by user-specified top/bottom straight lengths",
          "Positive main-bar projections end at the requested straight tangent; with hooks the bends lie outside that tangent",
          "Unspecified receiving slab, beam, footing or wall is NOT modelled by these free-end extensions",
          "BBS lengths are idealized centreline lengths; theoretical mass is length x bar section x 7850 kg/m3",
          "Native IFC 0.5.9 computes BarLength from longest mesh extent; BBS CSV is authoritative for bent bars",
          "Column and beam are independent assemblies: beam-column joint reinforcement is not checked"],
    }
    (out_dir/(p.column_id+"_Metadata.json")).write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"GO RC Column v{VERSION}: SUCCESS | {parent.name}")
    print(f"Concrete: {volume:.3f} m3 | Formwork contact: {formwork_contact:.3f} m2")
    print(f"Longitudinal: {len(positions)} bars | " +
          (f"Spiral: {spiral_info['turns']} turns, pitch {spiral_info['pitch_actual_mm']:.1f} mm"
           if p.shape=="circular" else f"Ties: {len(tie_stations)}"))
    print(f"Steel mass (theoretical): {total_steel:.3f} kg | prototypes: {metadata['mesh_prototypes']}")
    step(97, "บันทึกโมเดล / Publish scene")
    if p.native_bim_visible:
        result=scene_adapter.publish_native_bim(scene,parent,prefix=p.column_id)
        print("Native BIM top-level tagged leaves:",result["tagged"],
              "(native parent hierarchy replaced by logical grouping)")
    else:
        scene_adapter.publish_assembly(scene,parent)
        print("Native assembly: ONE top-level group | use GO RC BIM Browser")
    print("Output:",out_dir)
    step(100, "สร้างเสาสำเร็จ / Build complete")
    if ((p.main_hook_top and p.main_hook_top_direction == "outward") or
        (p.main_hook_bottom and p.main_hook_bottom_direction == "outward")):
        print("WARNING: outward hooks extend beyond column boundary; check footing/slab/joint concrete independently")
    if p.main_top_projection_mm or p.main_bottom_projection_mm:
        print(f"Main vertical projections: TOP +{p.main_top_projection_mm:.1f} mm | "
              f"BOTTOM -{p.main_bottom_projection_mm:.1f} mm (beyond concrete faces)")
        print("WARNING: receiving beam/slab/footing concrete is NOT modelled or checked")
    print("NOT CHECKED: engineering code compliance, anchorage, lap, fabrication BBS")
    return metadata

