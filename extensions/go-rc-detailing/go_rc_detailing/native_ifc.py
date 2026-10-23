"""GO RC Detailing v0.8.2: IngeTrazo 0.5.9 *native* IFC4 bridge.

This module DOES NOT edit the generated STEP text. It delegates IFC class
serialization and quantity sets to formats.ifc.save_ifc.

Important: IngeTrazo 0.5.9 native `IfcReinforcingBar` quantitative fields
use the largest axis-aligned bounding-box extent as BarLength and infer the
NominalDiameter from its closed mesh volume. That approximation is ONLY
appropriate for straight bars. Bent bars require GO's separately generated
centreline BBS. The native IFC must not be used as a fabrication cut list.

The visible model remains nested with mesh instancing. Only *temporary*
flat, world-space copies are passed to the existing native exporter because
core.bim.collect_objects() in v0.5.9 reads only top-level tagged groups.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from types import SimpleNamespace


def require_native_bim():
    """Fail explicitly on legacy/unsupported builds rather than corrupt IFC."""
    from core.bim import IFC_CLASSES
    from core.version import __version__
    version = tuple(int(x) for x in re.findall(r"\d+", __version__)[:3])
    if version < (0, 5, 9) or "IfcReinforcingBar" not in IFC_CLASSES:
        raise RuntimeError(
            "GO RC Detailing v0.8.2 requires IngeTrazo >= 0.5.9 with "
            "native IfcReinforcingBar. Found: " + str(__version__))
    return __version__


def _safe_mesh_extents(mesh):
    # Reading an already-built mesh does not recompute its geometry. The
    # native exporter uses maximum x/y/z extent as bar length (#495).
    points = [v.position for v in mesh.vertices]
    if not points:
        return None
    return max(
        max(getattr(p, ax)() for p in points) - min(getattr(p, ax)() for p in points)
        for ax in ("x", "y", "z")
    )


def _flat_from_beam_groups(items):
    from core.group import Group, world_mesh
    for g in items:
        if getattr(g, "ifc", None) is None:
            continue  # visual supports and verification markers
        clone = Group(world_mesh(g), name=g.name)
        clone.ifc = dict(g.ifc)
        yield clone


def _flat_from_assembly(root):
    from core.group import Group, iter_placements, transformed_mesh
    for item, matrix in iter_placements(root):
        if not getattr(item, "ifc", None):
            continue
        if not item.mesh.faces:
            continue
        m = transformed_mesh(item.mesh, matrix) if matrix is not None else item.mesh
        clone = Group(m, name=item.name)
        clone.ifc = dict(item.ifc)
        yield clone


def _has_bend(meta):
    """BBS centreline length is authoritative for bent rebar."""
    kind = str(meta.get("kind", "")).lower()
    shape = str(meta.get("bar_shape", meta.get("shape", ""))).lower()
    if kind in ("spiral", "helix") or "helix" in shape or "spiral" in shape:
        return True
    if kind in ("main", "top", "bottom", "extra_top", "extra_bottom", "stirrup", "tie"):
        # Column main is always straight in v0.8.2 and has no explicit shape.
        return kind != "main" or bool(shape) and shape not in ("straight", "go-c-straight")
    return bool(meta.get("hook_deg") or meta.get("end_hooks") or meta.get("bend_radius_m"))


def _write_bar_reconciliation(path, groups, bar_metadata):
    """Append-only independent schedule of questionable native lengths.

    This deliberately does NOT claim to validate IFC fabrication lengths.
    All units of length are metres except explicit diameters (mm).
    """
    fields = ("bar", "diameter_mm", "bbs_centerline_length_m", "native_bbox_length_m",
              "difference_m", "native_length_is_fabrication_safe", "message")
    rows = []
    for g in groups:
        if g.name not in bar_metadata:
            continue
        meta = bar_metadata[g.name]
        native_len = _safe_mesh_extents(g.mesh)
        bbs_len = float(meta["length_m"])
        bent = _has_bend(meta)
        note = ("BENT GEOMETRY: IFC BarLength is native axis-aligned bounding extent; "
                "do NOT use for cutting. Refer to GO BBS (preliminary)." if bent else
                "Straight bar: native bbox approximation; independently verify IFC values.")
        rows.append({
            "bar": g.name,
            "diameter_mm": meta["diameter_mm"],
            "bbs_centerline_length_m": round(bbs_len, 8),
            "native_bbox_length_m": "" if native_len is None else round(native_len, 8),
            "difference_m": "" if native_len is None else round(bbs_len-native_len, 8),
            "native_length_is_fabrication_safe": "NO",
            "message": note,
        })
    if len(rows) != len(bar_metadata):
        missing = set(bar_metadata) - {r["bar"] for r in rows}
        raise ValueError("Native IFC bridge did not receive all tagged rebar: " + str(sorted(missing)[:8]))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _export(groups, target, bar_meta, form_meta, project_name):
    from core.mesh import Mesh
    from formats.ifc import save_ifc
    require_native_bim()
    target = Path(target)
    visible = list(groups)
    if not visible:
        raise ValueError("No BIM leaf objects to export")
    by_name = {g.name: g for g in visible}
    if len(by_name) != len(visible):
        raise ValueError("Duplicate BIM leaf names: IFC quantities cannot be reconciled")
    expected = set(bar_meta) | set(form_meta)
    if not expected.issubset(by_name):
        raise ValueError("Missing BIM rebar or formwork tags: " + str(sorted(expected - set(by_name))[:8]))
    for name in bar_meta:
        if by_name[name].ifc.get("class") != "IfcReinforcingBar":
            raise ValueError("Native rebar IFC class required: " + name)
    temp = SimpleNamespace(loose_mesh=Mesh(), groups=visible)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Export with the final basename so IFC FILE_NAME points to the right file.
    count = save_ifc(temp, target, project_name=project_name)
    if count != len(visible):
        target.unlink(missing_ok=True)
        raise ValueError(f"Native IFC exported {count} elements, expected {len(visible)}")
    text = target.read_text(encoding="ascii")
    n_rebar = len(re.findall(r"=IFCREINFORCINGBAR\(", text))
    if n_rebar != len(bar_meta):
        target.unlink(missing_ok=True)
        raise ValueError(f"Native IFC reinforcing bars={n_rebar}, expected={len(bar_meta)}")
    audit_file = target.with_name(target.stem + "_Rebar_IFC_vs_BBS.csv")
    rows = _write_bar_reconciliation(audit_file, visible, bar_meta)
    bad = sum("BENT" in r["message"] for r in rows)
    print(f"GO native IFC4 v0.5.9: {count} elements / {n_rebar} IfcReinforcingBar; no STEP patch")
    print(f"Native IFC BarLength warning: {bad} bent bars must use independent GO BBS, NOT IFC length")
    print("IFC vs BBS reconciliation:", audit_file)
    return {"elements": count, "bars": n_rebar, "bent": bad, "audit": str(audit_file)}


def export_beam_native(groups, target, bars, formwork):
    """Adapter with the exact v0.7 `export_beam_ifc` signature."""
    return _export(_flat_from_beam_groups(groups), target, bars, formwork,
                   "GO RC Beam | Native IFC 0.5.9")


def export_column_native(parent, target, bars, formwork, identifier):
    """Column export: collect nested tags without changing UI instancing."""
    return _export(_flat_from_assembly(parent), target, bars, formwork,
                   "GO RC Column " + str(identifier) + " | Native IFC 0.5.9")
