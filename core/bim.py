# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
"""BIM tagging layer — semantics ON TOP of freeform geometry.

The project's non-negotiable principle: the modeller is push/pull
freedom, and BIM lives as *metadata applied to selected geometry* (the
BlenderBIM pattern), never as rigid Revit-style primitives. A tag turns a set
of faces (or a whole group) into a named IFC object; tagged objects feed the
quantity takeoff — and later the IFC export to IngePresupuestos. Untagged
geometry stays plain drawing.

Storage:
- loose faces: ``face.attrs["ifc"] = {"id": n, "class": ..., "name": ...}``
  — the ``attrs`` dict already survives the engine's face churn (push/pull,
  rebuilds, heals) and serialises with the document, so tags are durable.
- groups: ``group.ifc = {"class": ..., "name": ...}`` (the group IS the
  object; its isolated mesh gives exact quantities).

Quantities are computed honestly: any face set yields its AREA; VOLUME is
reported only when the set is watertight on its own (every edge of the set
bordered by exactly two faces of the set) — the guarantee the whole engine
exists to provide.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QMatrix4x4, QVector3D

#: Curated civil/architecture classes (IFC4 names).
IFC_CLASSES = [
    "IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcFooting",
    "IfcRoof", "IfcStair", "IfcRamp", "IfcDoor", "IfcWindow",
    "IfcRailing", "IfcCovering", "IfcPile", "IfcMember", "IfcSpace",
    "IfcReinforcingBar",
]

#: Density of reinforcing steel, kg/m³ — the bar's weight is its volume
#: times this, as a takeoff bills it.
STEEL_DENSITY = 7850.0


def next_object_id(scene) -> int:
    """A fresh BIM object id (max existing + 1)."""
    top = 0
    for f in scene.loose_mesh.faces:
        tag = f.attrs.get("ifc")
        if tag and isinstance(tag.get("id"), int):
            top = max(top, tag["id"])
    return top + 1


def tag_faces(faces, ifc_class: str, name: str, obj_id: int) -> None:
    for f in faces:
        f.attrs["ifc"] = {"id": obj_id, "class": ifc_class, "name": name}


def untag_faces(faces) -> None:
    for f in faces:
        f.attrs.pop("ifc", None)


def tag_group(group, ifc_class: str, name: str) -> None:
    group.ifc = {"class": ifc_class, "name": name}


def untag_group(group) -> None:
    group.ifc = None


def face_set_area(faces) -> float:
    return sum(f.area() for f in faces)


def _loop_area(loop) -> float:
    """Planar area of a vertex loop (half the Newell normal's length)."""
    n = QVector3D(0.0, 0.0, 0.0)
    count = len(loop)
    for i in range(count):
        curr = loop[i].position
        nxt = loop[(i + 1) % count].position
        n = n + QVector3D(
            (curr.y() - nxt.y()) * (curr.z() + nxt.z()),
            (curr.z() - nxt.z()) * (curr.x() + nxt.x()),
            (curr.x() - nxt.x()) * (curr.y() + nxt.y()),
        )
    return 0.5 * n.length()


def face_net_area(f) -> float:
    """Face area with hole loops (door/window openings) subtracted."""
    area = f.area()
    for h in f.hole_loops:
        area -= _loop_area(h)
    return max(area, 0.0)


def face_set_volume(faces):
    """Volume enclosed by ``faces``, or ``None`` when the set is not
    watertight by itself. Signed tetrahedron sum over the set's triangles;
    closure = every edge of the set borders exactly two faces of the set."""
    faces = list(faces)
    if not faces:
        return None
    fset = set(faces)
    counts: dict = {}
    for f in faces:
        for lp in (f.loop, *f.hole_loops):
            n = len(lp)
            for i in range(n):
                key = frozenset((id(lp[i]), id(lp[(i + 1) % n])))
                counts[key] = counts.get(key, 0) + 1
    if any(c != 2 for c in counts.values()):
        return None
    total = 0.0
    for f in faces:
        for t0, t1, t2 in f.triangulate():
            total += QVector3D.dotProduct(
                t0, QVector3D.crossProduct(t1, t2)) / 6.0
    return abs(total)


class QuantityCache:
    """Measurements shared by equivalent placements during one content revision.

    Translation does not change any takeoff quantity. Leaf placements with
    the same prototype and linear transform therefore use one measurement
    mesh, even when thousands of objects have different positions and BIM
    names. Rotations and scales remain part of the key: several class
    quantities depend on world-axis extents or upward-facing surfaces.

    Keep this cache only while document content is unchanged. Mesh edits,
    metadata edits, undo/redo and document replacement must start a new
    cache; selection changes may reuse it. ``collect_objects`` creates a
    fresh cache on every call, so direct callers cannot observe stale data.
    """

    def __init__(self):
        self._meshes = {}
        self._measurements = {}
        self._quantities = {}
        self._solids = {}

    def _geometry(self, group):
        from core.group import transformed_mesh, world_mesh

        matrix = getattr(group, "xform", None)
        if (getattr(group, "children", None)
                or (matrix is not None and not matrix.isAffine())):
            # Nested placements have relative offsets that affect the
            # object's extents; measure their complete world-space mesh.
            key = group
            if key not in self._meshes:
                self._meshes[key] = world_mesh(group)
            return key, self._meshes[key]

        linear = None
        if matrix is not None:
            linear = tuple(matrix(row, col) for row in range(3) for col in range(3))
            if linear == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0):
                linear = None
        key = (group.mesh, linear)
        if key not in self._meshes:
            if linear is None:
                mesh = group.mesh
            else:
                a, b, c, d, e, f, g, h, i = linear
                transform = QMatrix4x4(a, b, c, 0.0,
                                      d, e, f, 0.0,
                                      g, h, i, 0.0,
                                      0.0, 0.0, 0.0, 1.0)
                mesh = transformed_mesh(group.mesh, transform)
            self._meshes[key] = mesh
        return key, self._meshes[key]

    def group_quantities(self, group, ifc_class):
        """Return area, volume and class quantities for a placed group."""
        key, mesh = self._geometry(group)
        if key not in self._measurements:
            faces = list(mesh.faces)
            self._measurements[key] = (faces, face_set_area(faces), face_set_volume(faces))
        faces, area, volume = self._measurements[key]
        qkey = (key, ifc_class)
        if qkey not in self._quantities:
            self._quantities[qkey] = class_quantities(
                ifc_class, faces, _measured=(area, volume))
        return area, volume, self._quantities[qkey]

    def solid_volume(self, group):
        """Entity Info's stricter solid check, shared by equal prototypes."""
        from core.solids import solid_report

        if getattr(group, "children", None):
            return None  # Preserve Solid Tools' no-nested-groups rule.
        key, mesh = self._geometry(group)
        if key not in self._solids:
            ok, volume = solid_report(mesh)
            self._solids[key] = volume if ok else None
        return self._solids[key]


def collect_objects(scene) -> list[dict]:
    """Every tagged BIM object in the document, with live quantities:
    ``{"key", "class", "name", "area", "volume" (or None), "faces" | "group"}``.
    Loose-face objects group by tag id; each tagged group is one object.
    ``quantities`` contains the already-measured class quantity tuple; use it
    instead of measuring a component's untransformed prototype again."""
    out: list[dict] = []
    cache = QuantityCache()
    by_id: dict = {}
    for f in scene.loose_mesh.faces:
        tag = f.attrs.get("ifc")
        if tag:
            by_id.setdefault(tag.get("id"), (tag, []))[1].append(f)
    for obj_id, (tag, faces) in sorted(by_id.items(),
                                       key=lambda kv: kv[0] or 0):
        area, volume = face_set_area(faces), face_set_volume(faces)
        ifc_class = tag.get("class", "")
        out.append({
            "key": ("faces", obj_id),
            "class": ifc_class,
            "name": tag.get("name", ""),
            "area": area,
            "volume": volume,
            "quantities": class_quantities(ifc_class, faces, _measured=(area, volume)),
            "faces": faces,
        })
    for g in scene.groups:
        tag = getattr(g, "ifc", None)
        if not tag:
            continue
        ifc_class = tag.get("class", "")
        area, volume, quantities = cache.group_quantities(g, ifc_class)
        out.append({
            "key": ("group", id(g)),
            "class": ifc_class,
            "name": tag.get("name", ""),
            "area": area,
            "volume": volume,
            "quantities": quantities,
            "group": g,
        })
    return out


#: Standard IFC4 quantity-set name per class (falls back to BaseQuantities).
QSET_NAMES = {
    "IfcWall": "Qto_WallBaseQuantities",
    "IfcSlab": "Qto_SlabBaseQuantities",
    "IfcColumn": "Qto_ColumnBaseQuantities",
    "IfcBeam": "Qto_BeamBaseQuantities",
    "IfcFooting": "Qto_FootingBaseQuantities",
    "IfcRoof": "Qto_RoofBaseQuantities",
    "IfcStair": "Qto_StairBaseQuantities",
    "IfcRamp": "Qto_RampBaseQuantities",
    "IfcDoor": "Qto_DoorBaseQuantities",
    "IfcWindow": "Qto_WindowBaseQuantities",
    "IfcRailing": "Qto_RailingBaseQuantities",
    "IfcCovering": "Qto_CoveringBaseQuantities",
    "IfcPile": "Qto_PileBaseQuantities",
    "IfcMember": "Qto_MemberBaseQuantities",
    "IfcSpace": "Qto_SpaceBaseQuantities",
    "IfcReinforcingBar": "Qto_ReinforcingElementBaseQuantities",
}

#: Budget unit each class is measured in (the metrado unit downstream tools
#: like IngePresupuestos bill by): m2 = surface partidas, m3 = concrete,
#: m = linear elements, und = counted units.
METRADO_UNIT = {
    "IfcWall": "m2", "IfcSlab": "m2", "IfcRoof": "m2", "IfcStair": "m2",
    "IfcRamp": "m2", "IfcCovering": "m2", "IfcSpace": "m2",
    "IfcColumn": "m3", "IfcBeam": "m3", "IfcFooting": "m3",
    "IfcPile": "m", "IfcMember": "m", "IfcRailing": "m",
    "IfcDoor": "und", "IfcWindow": "und",
    "IfcReinforcingBar": "kg",
}


def _extents(faces):
    """World-axis extents (dx, dy, dz) of a face set's vertices."""
    xs, ys, zs = [], [], []
    for f in faces:
        for lp in (f.loop, *f.hole_loops):
            for v in lp:
                p = v.position
                xs.append(p.x()), ys.append(p.y()), zs.append(p.z())
    if not xs:
        return 0.0, 0.0, 0.0
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _upward_net_area(faces, closed: bool) -> float:
    """Net area of the upward-facing faces (roof slopes, stair treads).
    On a watertight set normals are outward-consistent so the sign is
    trusted; on open sheets the winding is arbitrary, so |nz| decides."""
    total = 0.0
    for f in faces:
        nz = f.normal().z()
        if (nz if closed else abs(nz)) > 0.2:
            total += face_net_area(f)
    return total


def _face_width_height(f):
    """In-plane horizontal and vertical extents of a face — the honest
    OverallWidth/OverallHeight of a door or window drawn in any wall
    orientation. Falls back to bbox extents for horizontal faces."""
    n = f.normal()
    u = QVector3D.crossProduct(QVector3D(0.0, 0.0, 1.0), n)
    if u.length() < 1e-6:                       # face lies flat
        dx, dy, dz = _extents([f])
        return max(dx, dy), dz
    u = u.normalized()
    us = [QVector3D.dotProduct(v.position, u) for v in f.loop]
    zs = [v.position.z() for v in f.loop]
    return max(us) - min(us), max(zs) - min(zs)


def class_quantities(ifc_class: str, faces, *, _measured=None):
    """Standard per-class BaseQuantities from freeform geometry, honestly:
    every value is measured off the tagged faces (volume only when the set
    is watertight on its own), named as the IFC4 ``Qto_*`` sets so any
    downstream consumer — IngePresupuestos included — reads the metrado
    straight from the file.

    Returns ``(qset_name, entries, metrado)`` where ``entries`` is a list of
    ``(kind, name, value)`` with kind in {"area", "volume", "length",
    "weight"} and
    ``metrado`` is ``(value, unit)`` in the class's budget unit (value may
    be ``None`` when not computable, e.g. volume of an open set)."""
    faces = list(faces)
    unit = METRADO_UNIT.get(ifc_class, "m2")
    if not faces:
        return QSET_NAMES.get(ifc_class, "BaseQuantities"), [], (None, unit)
    if _measured is None:
        total, volume = face_set_area(faces), face_set_volume(faces)
    else:
        total, volume = _measured
    closed = volume is not None
    dx, dy, dz = _extents(faces)
    big = max(faces, key=lambda f: f.area())
    entries: list[tuple[str, str, float]] = []

    def add(kind, name, value):
        if value is not None and value > 1e-9:
            entries.append((kind, name, float(value)))

    metrado = None
    if ifc_class == "IfcWall":
        side_gross = big.area()
        side_net = face_net_area(big)
        add("length", "Height", dz)
        if dz > 1e-9:
            add("length", "Length", side_gross / dz)
        if side_net > 1e-9 and closed:
            add("length", "Width", volume / side_net)
        add("area", "GrossSideArea", side_gross)
        add("area", "NetSideArea", side_net)
        add("volume", "GrossVolume", volume)
        metrado = side_net
    elif ifc_class == "IfcSlab":
        gross = big.area()
        net = face_net_area(big)
        perim = sum((big.loop[i].position
                     - big.loop[(i + 1) % len(big.loop)].position).length()
                    for i in range(len(big.loop)))
        add("length", "Perimeter", perim)
        if net > 1e-9 and closed:
            add("length", "Width", volume / net)
        add("area", "GrossArea", gross)
        add("area", "NetArea", net)
        add("volume", "GrossVolume", volume)
        metrado = net
    elif ifc_class in ("IfcRoof", "IfcStair", "IfcRamp"):
        up = _upward_net_area(faces, closed)
        add("length", "Length", max(dx, dy))
        add("area", "GrossArea", up)
        add("volume", "GrossVolume", volume)
        metrado = up
    elif ifc_class == "IfcColumn":
        add("length", "Length", dz)
        if dz > 1e-9 and closed:
            add("area", "CrossSectionArea", volume / dz)
        add("volume", "GrossVolume", volume)
        metrado = volume
    elif ifc_class == "IfcBeam":
        length = max(dx, dy, dz)
        add("length", "Length", length)
        if length > 1e-9 and closed:
            add("area", "CrossSectionArea", volume / length)
        add("volume", "GrossVolume", volume)
        metrado = volume
    elif ifc_class == "IfcFooting":
        add("length", "Height", dz)
        add("area", "GrossSurfaceArea", total)
        add("volume", "GrossVolume", volume)
        metrado = volume
    elif ifc_class == "IfcPile":
        add("length", "Length", dz)
        add("volume", "GrossVolume", volume)
        metrado = dz
    elif ifc_class in ("IfcMember", "IfcRailing"):
        length = max(dx, dy) if ifc_class == "IfcRailing" else max(dx, dy, dz)
        add("length", "Length", length)
        add("volume", "GrossVolume", volume)
        metrado = length
    elif ifc_class == "IfcReinforcingBar":
        # A straight bar (#495): its length is the longest extent, its
        # diameter the round section that holds its volume, its weight the
        # steel in it -- reinforcement is billed by the kilo.
        length = max(dx, dy, dz)
        add("length", "Length", length)
        if closed and length > 1e-9:
            add("length", "NominalDiameter",
                2.0 * (volume / (math.pi * length)) ** 0.5)
            add("weight", "Weight", volume * STEEL_DENSITY)
            metrado = volume * STEEL_DENSITY
    elif ifc_class == "IfcCovering":
        net = sum(face_net_area(f) for f in faces)
        add("area", "GrossArea", total)
        add("area", "NetArea", net)
        metrado = net
    elif ifc_class in ("IfcDoor", "IfcWindow"):
        width, height = _face_width_height(big)
        add("length", "Width", width)
        add("length", "Height", height)
        add("area", "Area", face_net_area(big))
        metrado = 1.0
    elif ifc_class == "IfcSpace":
        floor = max((face_net_area(f) for f in faces
                     if abs(f.normal().z()) > 0.7), default=0.0)
        add("length", "Height", dz)
        add("area", "NetFloorArea", floor)
        add("volume", "GrossVolume", volume)
        metrado = floor
    else:
        add("area", "GrossArea", total)
        add("volume", "GrossVolume", volume)
        metrado = total
    if metrado is not None and metrado <= 1e-9:
        metrado = None
    return QSET_NAMES.get(ifc_class, "BaseQuantities"), entries, (metrado, unit)


def quantities_csv(scene) -> str:
    """The takeoff table (metrado) as CSV — the pre-IFC bridge to
    IngePresupuestos: model → budget quantities in one export. ``metrado``
    is the per-class budget measure (wall face m², column m³, pile m,
    door und); area/volume stay as the raw shell numbers."""
    lines = ["class,name,metrado,unit,area_m2,volume_m3"]
    for obj in collect_objects(scene):
        _, _, (metrado, unit) = obj["quantities"]
        met = "" if metrado is None else f"{metrado:.4f}"
        vol = "" if obj["volume"] is None else f"{obj['volume']:.4f}"
        name = (obj["name"] or "").replace('"', "'")
        lines.append(f"{obj['class']},\"{name}\",{met},{unit},"
                     f"{obj['area']:.4f},{vol}")
    return "\n".join(lines) + "\n"
