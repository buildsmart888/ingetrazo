"""GO Engineering | RC beam BIM + verification demo v0.7.0 for IngeTrazo (Python Console).

Purpose
-------
A corrected single-corner 90/135-degree hook detailing beam demo for IngeTrazo with:
- concrete in cleaner gray
- longitudinal bars with 90-degree hooks both ends
- stirrups with non-crossing 135-degree hook returns at ONE upper corner
- 90-degree stirrups with true perpendicular returns at the SAME upper-left corner
- dense support-zone spacing + midspan spacing
- BBS CSV + BOQ CSV + IFC patch for IngeTrazo v0.5.8 compatibility
- logical beam package metadata for all generated groups

Run in IngeTrazo: Extensions > Python Console > Run script file...
"""
from __future__ import annotations

import csv
import os
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QMatrix4x4, QVector3D
from core.group import world_mesh
from core.layers import Layer
from core.sweep import sweep_profile
from core.textlabel import TextLabel
from formats.ifc import ifc_guid, save_ifc

# ----------------------------- CONFIG ---------------------------------------
# Values below are the defaults shown in the parameter dialog.
BEAM_ID = "B1"
SPANS_M = [4.0]             # continuous beam spans, SUPPORT-CENTRE to SUPPORT-CENTRE
B = 0.30
H = 0.50
COVER = 0.040              # to OUTSIDE SURFACE of stirrup
END_COVER = 0.050          # main bar end centerline offset
TOP_COUNT, TOP_DB_MM = 2, 16
BOTTOM_COUNT, BOTTOM_DB_MM = 3, 20
STIRRUP_DB_MM = 9
STIRRUP_HOOK_DEG = 135     # 90 or 135 (nominal direction-change angle)
STIRRUP_HOOK_TAIL_MM = 90  # straight part AFTER the bend, not virtual vertex distance
FIRST_LEFT_M = 0.050      # stirrup centre offset from left support centre
FIRST_RIGHT_M = 0.050
LEFT_ZONE_M = 0.60
RIGHT_ZONE_M = 0.60
LEFT_SPACING_M = 0.100
MID_SPACING_M = 0.150
RIGHT_SPACING_M = 0.100
# Special reinforcing steel: top at every SUPPORT, bottom at every SPAN centre.
SPECIAL_TOP_COUNT, SPECIAL_TOP_DB_MM = 2, 16
SPECIAL_BOTTOM_COUNT, SPECIAL_BOTTOM_DB_MM = 2, 16
SPECIAL_TOP_FRACTION = 0.25        # each adjacent span at supports
SPECIAL_BOTTOM_FRACTION = 0.40     # centered in each span; keep separated from top extra hook cutoffs
SPECIAL_BAR_CLEAR_M = 0.025       # nominal layer separation (NOT code design)
# NEW v0.6: 90-degree hooks at BOTH ends of special top / bottom bars.
# Values are straight-centreline extensions AFTER the rounded bend.
SPECIAL_TOP_HOOK_TAIL_MM = 120
SPECIAL_BOTTOM_HOOK_TAIL_MM = 120
SPECIAL_HOOK_RADIUS_MULTIPLIER = 4.0   # bend centreline radius = multiplier * bar diameter
# Support reference geometry. Spans are measured SUPPORT-CENTRE to SUPPORT-CENTRE.
SUPPORT_WIDTH_M = 0.30          # along beam X; clear span is between COLUMN FACES
SUPPORT_DEPTH_M = 0.40          # across beam Y
SUPPORT_REFERENCE_HEIGHT_M = 1.00   # draw below soffit; zero rebar/BOQ quantities
SHOW_SUPPORT_MARKERS = True
# Optional per-span tie overrides: {span_number (1-based): {
#   'left_zone_m': 0.6, 'left_spacing_m': 0.1, 'mid_spacing_m': 0.15,
#   'right_zone_m': 0.6, 'right_spacing_m': 0.1,
#   'first_left_m': 0.05, 'first_right_m': 0.05}}
# Override only specified fields. Untouched fields use global defaults.
SPAN_TIE_OVERRIDES = {}
PLYWOOD_THICKNESS = 0.018
TUBE_SIDES = 12
CORNER_STEPS = 10
STEEL_DENSITY = 7850.0
TAG_KEY = "go_rc_beam"
OUT_BASE = Path.home() / "GO_Engineering" / "RC_Beam_Demo_v070"
WRITE_IFC = True
SHOW_MARK_LABELS = False  # off by default to avoid cluttered 3D models
SHOW_PARAMETER_DIALOG = os.environ.get("GO_RC_BEAM_SKIP_DIALOG") != "1"
EPS = 1e-9
# Verification is a geometric screen, not compliance certification.
VERIFY_MIN_LONGITUDINAL_CLEAR_MM = 25.0  # configured geometric threshold
VERIFY_COVER_TOL_MM = 0.70             # mesh/float representation tolerance
VERIFY_PENETRATION_TOL_MM = 0.75       # clashes below this are reported as contact only
VERIFY_MARKERS = True
VERIFY_SHOW_REPORT = os.environ.get("GO_RC_BEAM_SKIP_DIALOG") != "1"
VERIFY_MAX_MARKERS = 48
VERIFY_MARKER_SIZE_MM = 34
VERIFY_MAX_TABLE_ROWS = 400
# ---------------------------------------------------------------------------

assert "scene" in globals() and "Mesh" in globals() and "Group" in globals(), (
    "Open IngeTrazo > Extensions > Python Console > Run script file..."
)
P = QVector3D

# In IngeTrazo Python Console, `bim` is available in the live scope.


def db_m(db_mm):
    return db_mm / 1000.0


def steel_kg_per_m(db_mm):
    d = db_m(db_mm)
    return STEEL_DENSITY * math.pi * (d / 2.0) ** 2


def V(x, y, z=0.0):
    return QVector3D(x, y, z)


def _unit(v):
    l = v.length()
    return v / l if l > EPS else QVector3D(0, 0, 0)


def _dedupe(points, tol=1e-7):
    out = []
    for p in points:
        if not out or (p - out[-1]).length() > tol:
            out.append(p)
    return out


def _circular_profile(mesh, origin, direction, dia, sides):
    d = _unit(direction)
    if d.length() < EPS:
        d = QVector3D(0, 0, 1)
    ref = QVector3D(0, 0, 1)
    if abs(QVector3D.dotProduct(d, ref)) > 0.99:
        ref = QVector3D(1, 0, 0)
    u = _unit(QVector3D.crossProduct(d, ref))
    w = _unit(QVector3D.crossProduct(d, u))
    r = dia / 2.0
    points = []
    for i in range(sides + 1):
        a = 2.0 * math.pi * i / sides
        points.append(origin + u * (r * math.cos(a)) + w * (r * math.sin(a)))
    return mesh.add_face(points)


def _fillet_corner(p0, p1, p2, r, segments=8):
    a1, a2 = p0 - p1, p2 - p1
    L1, L2 = a1.length(), a2.length()
    if L1 < EPS or L2 < EPS or r <= 0:
        return [p1]
    v1, v2 = a1 / L1, a2 / L2
    dot = max(-1.0, min(1.0, QVector3D.dotProduct(v1, v2)))
    angle = math.acos(dot)
    if angle < 1e-4 or abs(angle - math.pi) < 1e-4:
        return [p1]
    half = math.tan(angle / 2.0)
    t = r / half
    max_t = 0.5 * min(L1, L2)
    if t > max_t:
        t = max_t
        r = t * half
    t1, t2 = p1 + v1 * t, p1 + v2 * t
    bisector = _unit(v1 + v2)
    if bisector.length() < EPS:
        return [p1]
    center = p1 + bisector * (r / math.sin(angle / 2.0))
    u = t1 - center
    v = t2 - center
    n = _unit(QVector3D.crossProduct(u, v))
    if n.length() < EPS:
        return [p1]
    u_ortho = _unit(QVector3D.crossProduct(n, u)) * u.length()
    arc = math.pi - angle
    return [center + u * math.cos(arc * i / segments) + u_ortho * math.sin(arc * i / segments)
            for i in range(segments + 1)]


def _fillet_polyline(points, r, segments=8, closed=False):
    pts = _dedupe(points)
    n = len(pts)
    if n < 3 or r <= 0:
        return list(pts)
    out = []
    if closed:
        rng = range(n)
    else:
        out.append(pts[0])
        rng = range(1, n - 1)
    for i in rng:
        out.extend(_fillet_corner(pts[i - 1], pts[i], pts[(i + 1) % n], r, segments))
    if not closed:
        out.append(pts[-1])
    return out


def path_length(points):
    pts = list(points)
    return sum((pts[i + 1] - pts[i]).length() for i in range(len(pts) - 1))


def make_rebar_mesh(points, dia_m, fillet_r, color, closed=False, sides=TUBE_SIDES, segments=CORNER_STEPS):
    path = _fillet_polyline(points, fillet_r, segments, closed)
    if len(path) < 2:
        raise ValueError("Rebar path must contain at least 2 points")
    mesh_obj = Mesh()
    face = _circular_profile(mesh_obj, path[0], path[1] - path[0], dia_m, sides)
    ok=sweep_profile(mesh_obj, face, path, closed=closed)
    if not ok:
        raise ValueError('Sweep failed to construct a valid rebar solid; adjust hook dimensions')
    for f in mesh_obj.faces:
        f.attrs["color"] = color
    for e in mesh_obj.edges:
        e.soft = True
    return mesh_obj, path_length(path)


def coloured_face(target, xyzs, color, opacity=None):
    f = target.add_face(list(xyzs))
    f.attrs["color"] = color
    if opacity is not None:
        f.attrs["opacity"] = opacity
    return f


def solid_box(x0, y0, z0, x1, y1, z1, color, opacity=1.0):
    m = Mesh()
    faces = [
        [(x0,y1,z0),(x1,y1,z0),(x1,y0,z0),(x0,y0,z0)],
        [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)],
        [(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)],
        [(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)],
        [(x1,y1,z0),(x0,y1,z0),(x0,y1,z1),(x1,y1,z1)],
        [(x0,y1,z0),(x0,y0,z0),(x0,y0,z1),(x0,y1,z1)],
    ]
    for loop in faces:
        coloured_face(m, (P(*p) for p in loop), color, opacity)
    return m


def check_inputs():
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", BEAM_ID):
        raise ValueError("Beam ID: use letters, numbers, underscore or hyphen only")
    if not 1 <= len(SPANS_M) <= 12:
        raise ValueError("Provide 1-12 positive span lengths")
    if any(not math.isfinite(s) or s < 1.0 or s > 30 for s in SPANS_M):
        raise ValueError("Each span must be 1-30 m")
    if B < 0.15 or H < 0.20 or COVER < 0.02:
        raise ValueError("Check beam width, depth and concrete cover")
    if STIRRUP_HOOK_DEG not in (90,135):
        raise ValueError("Stirrup hook angle must be 90 or 135")
    if STIRRUP_DB_MM <= 0 or STIRRUP_HOOK_TAIL_MM <= 0:
        raise ValueError("Stirrup diameter and hook tail length must be positive")
    if not 0.05 <= SPECIAL_TOP_FRACTION <= 0.45 or not 0.10 <= SPECIAL_BOTTOM_FRACTION <= 0.75:
        raise ValueError("Invalid extra-bar support/central fractions")
    if min(FIRST_LEFT_M, FIRST_RIGHT_M, LEFT_SPACING_M, MID_SPACING_M,
           RIGHT_SPACING_M, LEFT_ZONE_M, RIGHT_ZONE_M, END_COVER) <= 0:
        raise ValueError("Stirrup zone and cover values must be positive")
    if min(TOP_COUNT, BOTTOM_COUNT) < 2:
        raise ValueError("Main steel needs at least 2 bars on each face")
    if min(SPECIAL_TOP_COUNT, SPECIAL_BOTTOM_COUNT) < 0:
        raise ValueError("Negative extra bar quantity")
    if not (SUPPORT_WIDTH_M > 0 and SUPPORT_DEPTH_M > 0 and
            SUPPORT_REFERENCE_HEIGHT_M > 0):
        raise ValueError("Support reference dimensions must be positive")
    if SPECIAL_HOOK_RADIUS_MULTIPLIER < 2 or SPECIAL_HOOK_RADIUS_MULTIPLIER > 12:
        raise ValueError("Extra bar hook radius multiplier must be between 2 and 12")
    if SPECIAL_TOP_COUNT and SPECIAL_TOP_HOOK_TAIL_MM <= 0:
        raise ValueError("Extra TOP hook straight-tail length must be positive")
    if SPECIAL_BOTTOM_COUNT and SPECIAL_BOTTOM_HOOK_TAIL_MM <= 0:
        raise ValueError("Extra BOTTOM hook straight-tail length must be positive")
    for span_i in range(1,len(SPANS_M)+1):
        cfg = get_span_tie_config(span_i)
        if any(v <= 0 for v in cfg.values()):
            raise ValueError(f"Span {span_i}: tie offsets, zones and spacings must be positive")
        if cfg['first_left_m'] < COVER+db_m(STIRRUP_DB_MM)+0.001 or cfg['first_right_m'] < COVER+db_m(STIRRUP_DB_MM)+0.001:
            raise ValueError(f"Span {span_i}: first stirrup centre must allow for hook X stagger beyond the support face")
        clear = SPANS_M[span_i-1] - SUPPORT_WIDTH_M
        if clear <= cfg['first_left_m']+cfg['first_right_m']+0.10:
            raise ValueError(f"Span {span_i}: not enough clear span between support faces for ties")
    if not isinstance(SPAN_TIE_OVERRIDES,dict) or any(not isinstance(k,int) or k < 1 or k > len(SPANS_M) for k in SPAN_TIE_OVERRIDES):
        raise ValueError("Per-span tie overrides must use existing 1-based span numbers")
    ds=db_m(STIRRUP_DB_MM)
    dm=max(db_m(TOP_DB_MM),db_m(BOTTOM_DB_MM),
           db_m(SPECIAL_TOP_DB_MM) if SPECIAL_TOP_COUNT else 0,
           db_m(SPECIAL_BOTTOM_DB_MM) if SPECIAL_BOTTOM_COUNT else 0)
    if B <= 2*(COVER+ds+dm/2+0.012) or H <= 2*(COVER+ds+dm/2+0.010):
        raise ValueError("Section too narrow/small for specified reinforcement")
    if END_COVER < COVER+0.5*max(db_m(TOP_DB_MM),db_m(BOTTOM_DB_MM)):
        raise ValueError("Main bar end cover is smaller than concrete cover+bar radius")
    # Reference detail supplied by the user: minimum extension 6db and 75 mm.
    # This validation follows that reference for the geometry prototype; it is
    # not a substitute for the governing design code's anchorage provisions.
    minimum_tail=max(6*db_m(STIRRUP_DB_MM),0.075)
    if STIRRUP_HOOK_TAIL_MM/1000.0+1e-10 < minimum_tail:
        raise ValueError(
            f"Hook straight tail must be at least max(6db,75mm) = {minimum_tail*1000:.1f}mm for this detailing reference")
    if any(g.name.startswith(BEAM_ID+"-") for g in scene.groups):
        raise ValueError("Beam ID already exists in this document: use New or different ID")
    for count,db_mm,label in [(SPECIAL_TOP_COUNT,SPECIAL_TOP_DB_MM,'TOP'),
                              (SPECIAL_BOTTOM_COUNT,SPECIAL_BOTTOM_DB_MM,'BOTTOM')]:
        if count and db_mm<=0:
            raise ValueError(f'Extra {label} bar diameter must be positive')
    if SHOW_MARK_LABELS and len(SPANS_M) > 5:
        print("Note: many span labels may crowd the viewport; hide GO | Bar Marks layer")


def instanced_group(proto, name, tag_class, layer, dx=0, dy=0, dz=0, metadata=None):
    g = Group(proto, name=name)
    g.layer = layer
    g.xform = QMatrix4x4()
    g.xform.translate(dx, dy, dz)
    if tag_class:
        bim.tag_group(g, tag_class, name)
    ext = metadata or {}
    ext.setdefault("beam_id", BEAM_ID)
    g.ext = {TAG_KEY: ext}
    return g


def classic_group(m, name, tag_class, layer, metadata=None):
    g = Group(m, name=name)
    g.layer = layer
    if tag_class:
        bim.tag_group(g, tag_class, name)
    ext = metadata or {}
    ext.setdefault("beam_id", BEAM_ID)
    g.ext = {TAG_KEY: ext}
    return g

# ---------------------------- IFC PATCH -------------------------------------
def _step_fields(attributes):
    fields, first, depth, quoted = [], 0, 0, False
    i = 0
    while i < len(attributes):
        ch = attributes[i]
        if ch == "'":
            if quoted and i + 1 < len(attributes) and attributes[i + 1] == "'":
                i += 2
                continue
            quoted = not quoted
        elif not quoted:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced STEP parentheses")
            elif ch == "," and depth == 0:
                fields.append(attributes[first:i].strip())
                first = i + 1
        i += 1
    if quoted or depth:
        raise ValueError("Unbalanced STEP entity arguments")
    fields.append(attributes[first:].strip())
    return fields


def patch_export_quantities(ifc_path, bars_by_name, form_by_name):
    lines = ifc_path.read_text(encoding="ascii").splitlines()
    entities = {}
    names = {}
    for i, line in enumerate(lines):
        match = re.fullmatch(r"#(\d+)=([A-Z][A-Z0-9_]*)\((.*)\);", line)
        if not match:
            continue
        eid, kind, args = int(match[1]), match[2], _step_fields(match[3])
        entities[eid] = (i, kind, args)
        if kind in ("IFCBEAM", "IFCREINFORCINGBAR", "IFCBUILDINGELEMENTPROXY") and len(args) >= 8:
            names[eid] = args[2][1:-1].replace("''", "'") if args[2].startswith("'") else args[2]

    def update_entity(eid, kind, fields):
        line_number = entities[eid][0]
        entities[eid] = (line_number, kind, fields)
        lines[line_number] = f"#{eid}={kind}({','.join(fields)});"

    expected = set(bars_by_name) | set(form_by_name)
    missing = expected - set(names.values())
    if missing:
        raise ValueError("IFC missing named beam parts: " + repr(sorted(missing)[:6]))

    related_qsets = {}
    for eid, (_line, kind, fields) in entities.items():
        if kind != "IFCRELDEFINESBYPROPERTIES" or len(fields) != 6:
            continue
        ids = re.fullmatch(r"\(#(\d+)\)", fields[4])
        qset = re.fullmatch(r"#(\d+)", fields[5])
        if ids and qset:
            related_qsets.setdefault(int(ids[1]), []).append(int(qset[1]))

    next_id = max(entities) + 1
    appended = []
    deleted = set()

    def new_entity(kind, *fields):
        nonlocal next_id
        eid = next_id
        next_id += 1
        appended.append(f"#{eid}={kind}({','.join(fields)});")
        return eid

    upgraded = 0
    for eid, name in names.items():
        if name not in bars_by_name:
            continue
        _line, cls, fields = entities[eid]
        if cls == "IFCBUILDINGELEMENTPROXY":
            upgraded += 1
        info = bars_by_name[name]
        d = db_m(info["diameter_mm"])
        length = info["length_m"]
        weight = info["weight_kg"]
        role = ".LIGATURE." if info["kind"] == "stirrup" else ".MAIN."
        surface = ".PLAIN." if info["kind"] == "stirrup" else ".TEXTURED."
        fields = fields[:8] + ["$", f"{d:.8f}", f"{math.pi*d*d/4:.10f}", f"{length:.8f}", role, surface]
        update_entity(eid, "IFCREINFORCINGBAR", fields)
        qsets = [qid for qid in related_qsets.get(eid, []) if qid in entities and entities[qid][1] == "IFCELEMENTQUANTITY"]
        length_id = new_entity("IFCQUANTITYLENGTH", "'Length'", "$", "$", f"{length:.8f}", "$")
        dia_id = new_entity("IFCQUANTITYLENGTH", "'NominalDiameter'", "$", "$", f"{d:.8f}", "$")
        weight_id = new_entity("IFCQUANTITYWEIGHT", "'Weight'", "$", "$", f"{weight:.8f}", "$")
        refs = f"(#{length_id},#{dia_id},#{weight_id})"
        if qsets:
            qid = qsets[0]
            _qi, _qkind, old = entities[qid]
            old_refs = re.fullmatch(r"\((#\d+(?:,#\d+)*)\)", old[5])
            if old_refs:
                for ref in old_refs[1].split(","):
                    old_id = int(ref[1:])
                    if old_id in entities and entities[old_id][1].startswith("IFCQUANTITY"):
                        deleted.add(entities[old_id][0])
            update_entity(qid, "IFCELEMENTQUANTITY", [old[0], old[1], "'Qto_ReinforcingElementBaseQuantities'", old[3], old[4], refs])
        else:
            qty_id = new_entity("IFCELEMENTQUANTITY", f"'{ifc_guid()}'", "$", "'Qto_ReinforcingElementBaseQuantities'", "$", "$", refs)
            new_entity("IFCRELDEFINESBYPROPERTIES", f"'{ifc_guid()}'", "$", "$", "$", f"(#{eid})", f"#{qty_id}")

    for eid, name in names.items():
        if name not in form_by_name:
            continue
        qty_id = new_entity("IFCQUANTITYAREA", "'FormworkContactArea'", "$", "$", f"{form_by_name[name]:.8f}", "$")
        qset_id = new_entity("IFCELEMENTQUANTITY", f"'{ifc_guid()}'", "$", "'Qto_GOFormwork'", "$", "$", f"(#{qty_id})")
        new_entity("IFCRELDEFINESBYPROPERTIES", f"'{ifc_guid()}'", "$", "$", "$", f"(#{eid})", f"#{qset_id}")

    insert_at = max(i for i, line in enumerate(lines) if line == "ENDSEC;")
    cleaned = [line for i, line in enumerate(lines[:insert_at]) if i not in deleted]
    cleaned.extend(appended)
    cleaned.extend(lines[insert_at:])
    ifc_path.write_text("\n".join(cleaned) + "\n", encoding="ascii")
    return upgraded


def export_beam_ifc(groups, target, bars, formwork):
    temp = SimpleNamespace(loose_mesh=Mesh(), groups=[])
    for g in groups:
        if not getattr(g,'ifc',None):
            continue  # Untagged support markers must NOT appear in IFC.
        clone = Group(world_mesh(g), name=g.name)
        clone.ifc = dict(g.ifc) if g.ifc else None
        clone.layer = g.layer
        temp.groups.append(clone)
    staging = target.with_name(target.name + ".tmp")
    try:
        save_ifc(temp, staging, project_name="GO RC Beam " + BEAM_ID)
        upgraded = patch_export_quantities(staging, bars, formwork)
        staging.replace(target)
        if upgraded:
            print(f"IFC compatibility: converted {upgraded} legacy proxy bars to IfcReinforcingBar")
    finally:
        if staging.exists():
            staging.unlink()


# -------------------- geometry & detailing math -----------------------------

def supports_x():
    x = [0.0]
    for s in SPANS_M:
        x.append(x[-1]+s)
    return x


def tie_bar_clearance_mm(y, z, main_db_mm, polyline):
    """Conservative transverse clearance from longitudinal bar to tie.

    - The longitudinal bar extends along X, so minimum 3D distance to a
      station tie centreline cannot exceed its projected YZ distance.
    - Projecting to YZ is intentionally conservative at offset hook ends.
    - Returns surface-to-surface clearance in millimetres (0 = touching).
    """
    best=1e30
    for a,b in zip(polyline,polyline[1:]):
        dy=b.y()-a.y()
        dz=b.z()-a.z()
        dd=dy*dy+dz*dz
        t=max(0.,min(1.,((y-a.y())*dy+(z-a.z())*dz)/dd)) if dd>1e-15 else 0.
        best=min(best,math.hypot(y-a.y()-t*dy,z-a.z()-t*dz))
    r=(main_db_mm+STIRRUP_DB_MM)/2000.0
    return 1000.0*(best-r)


def nominal_steel_band_positions(count, diameter_mm, z, tie_r, tie_polyline):
    """Place all corner bars on a common Y line, NEVER auto-pull top bars in.

    The tie's rounded corners determine a common corner-bar station for top
    and bottom, even when DB differs. A conflict rejects the configuration;
    silently shifting the reinforcement to clear the hooks is not allowed.
    """
    if count < 1:
        return []
    d=db_m(diameter_mm)
    ymin,ymax,zmin,zmax=tie_parameters()
    # Top and bottom outside bars ALIGN at +/- (inside radius tangent point).
    lateral=ymax-tie_r
    if lateral < 0:
        raise ValueError('Tie bend radius leaves no room for main corner bars')
    yy=[0.0] if count==1 else [(-lateral+2*lateral*j/(count-1)) for j in range(count)]
    if count>1:
        clear_between=2*lateral/(count-1)-d
        if clear_between < 0.025-1e-9:
            raise ValueError(
                'Main/extra bar clear spacing below 25mm at fixed corner stations; '
                'increase beam width or reduce bar count/diameter')
    for y in yy:
        c=tie_bar_clearance_mm(y,z,diameter_mm,tie_polyline)
        if c < -0.25:
            raise ValueError(
                'Rebar and 90/135 stirrup centreline clash by {:.2f}mm '
                'at Y={:.1f}mm, Z={:.1f}mm. Increase B/H or change '
                'reinforcement/hook dimensions; main bars are NOT shifted.'.format(
                    -c,1000*y,1000*z))
    return yy


def inner_special_bar_positions(count,diameter_mm,z,tie_polyline):
    """Place ADDITIONAL bars in an inner symmetric row, unlike MAIN corners.

    Explicit inner-row placement avoids silently pulling the MAIN top bars
    away from their corners just to hide a clash with 135-degree hook returns.
    Uses a 25mm minimum horizontal clear spacing between special bars and
    rejects sections where the inner row cannot be placed without clashes.
    NOTE: this is geometric clearance checking, not an approved rebar design.
    """
    if count<1:
        return []
    d=db_m(diameter_mm)
    outer=tie_parameters()[1]-stirrup_bend_radius()
    if count==1:
        if tie_bar_clearance_mm(0,z,diameter_mm,tie_polyline)<-0.25:
            raise ValueError('Central special reinforcement clashes with tie hook')
        return [0.0]
    min_lateral=(count-1)*(d+0.025)/2.0
    # Prefer a narrower symmetric INNER row, while widening as necessary
    # to maintain its required clear spacing for more bars.
    preferred=max(0.60*outer,min_lateral)
    if preferred > outer+1e-9:
        raise ValueError('Too many special bars for available beam width (25mm clear)')
    n=max(1,int(math.ceil((outer-preferred)/0.0005)))
    for i in range(n+1):
        lateral=min(outer,preferred+i*0.0005)
        ys=[-lateral+2*lateral*j/(count-1) for j in range(count)]
        if min(tie_bar_clearance_mm(y,z,diameter_mm,tie_polyline) for y in ys)>=-0.25:
            return ys
    raise ValueError('Special reinforcement inner row hits the tie hook: increase B/H or revise layer spacing')


def stirrup_bend_radius():
    ds=db_m(STIRRUP_DB_MM)
    available=min(B-2*COVER-ds,H-2*COVER-ds)
    if available <= 4*ds:
        raise ValueError("Cross section too small for closed tie")
    r=3*ds
    # Radius is to CENTRELINE. Keep enough room for rounded corner.
    if 2*r >= available*0.5:
        raise ValueError("Cross section too narrow for specified stirrup bend radius")
    return r


def tie_parameters():
    d=db_m(STIRRUP_DB_MM)
    ymin=-B/2+COVER+d/2
    ymax= B/2-COVER-d/2
    zmin=COVER+d/2
    zmax=H-COVER-d/2
    return ymin,ymax,zmin,zmax


def hook_direction_angle(points):
    # Angle between the two straight leg headings of the UNSMOOTHED path.
    p0,p1,p2=points
    a=_unit(p1-p0)
    b=_unit(p2-p1)
    return math.degrees(math.acos(max(-1.,min(1., QVector3D.dotProduct(a,b)))))


def _hook_leg_distance_2d(a, b, c, d):
    """Shortest XY-plane distance between two hook-tail segments (in YZ).

    Valid for finite line segments, including intersections. Designed to
    detect actual cross-overs before forming a swept solid; a nonzero X
    shift must NOT be used as a workaround for crossed hooks.
    """
    def orient(p,q,r):
        return (q.y()-p.y())*(r.z()-p.z())-(q.z()-p.z())*(r.y()-p.y())
    o1,o2,o3,o4=(orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b))
    if o1*o2 < -1e-14 and o3*o4 < -1e-14:
        return 0.0
    def pt_seg(p,s,t):
        dy=t.y()-s.y(); dz=t.z()-s.z()
        ss=dy*dy+dz*dz
        u=max(0.0,min(1.0,((p.y()-s.y())*dy+(p.z()-s.z())*dz)/ss)) if ss>1e-16 else 0.0
        return math.hypot(p.y()-(s.y()+u*dy),p.z()-(s.z()+u*dz))
    return min(pt_seg(a,c,d),pt_seg(b,c,d),pt_seg(c,a,b),pt_seg(d,a,b))


def _segment_distance_3d(p0,p1,q0,q1):
    """Minimum distance of two finite spatial centreline segments."""
    u=p1-p0; v=q1-q0; w=p0-q0
    a=QVector3D.dotProduct(u,u); b=QVector3D.dotProduct(u,v)
    c=QVector3D.dotProduct(v,v); d=QVector3D.dotProduct(u,w)
    e=QVector3D.dotProduct(v,w); det=a*c-b*b
    s=0.;t=0.
    if det>1e-17:
        s=max(0.,min(1.,(b*e-c*d)/det))
    elif a>EPS:
        s=max(0.,min(1.,-d/a))
    if c>EPS:
        t=max(0.,min(1.,(b*s+e)/c))
    if a>EPS:
        s=max(0.,min(1.,(b*t-d)/a))
    if c>EPS:
        t=max(0.,min(1.,(b*s+e)/c))
    return (w+u*s-v*t).length()


def _minimum_polyline_distance_3d(line_a,line_b):
    if len(line_a)<2 or len(line_b)<2:
        return 1e9
    return min(_segment_distance_3d(a,c,b,d)
               for a,c in zip(line_a,line_a[1:])
               for b,d in zip(line_b,line_b[1:]))


def stirrup_shape_vertices():
    """ONE-PIECE stirrup; 135deg hook returns meet at UPPER-LEFT.

    Both ends turn down/inward from the UPPER-LEFT corner and remain one
    connected bar. Return B tangency is at the vertical side of the rounded
    upper-left bend (zmax - bend radius), not 60 mm lower as in v0.5.2.

    The two 135-degree return bends overlap in a 2D End View. The visualization
    staggers their bends and tails slightly along beam X to avoid intersecting
    3D swept tubes. Such out-of-plane staging is NOT a conventional planar
    fabrication shape; obtain an approved detailing configuration separately.

    Geometry formulas for return B (angle=135, tail L, radius R):
       t = R * tan(135/2)
       z_virt_B = z_top - R + t
       y_tip_B = y_left + (t + L) * sin(45)
       z_tip_B = z_virt_B - (t + L) * cos(45)
    The actual bend and straight tail are generated by a filleted centreline.
    """
    ymin,ymax,zmin,zmax=tie_parameters()
    d=db_m(STIRRUP_DB_MM)
    r=stirrup_bend_radius()
    tail=STIRRUP_HOOK_TAIL_MM/1000.0
    t=r*math.tan(math.radians(STIRRUP_HOOK_DEG/2.0))

    if STIRRUP_HOOK_DEG==135:
        # The SECOND return must reach the TOP-LEFT CORNER, not make a bend
        # ~60 mm below it (the v0.5.2 bug). The BEND START of Return B is
        # the vertical tangency at Z = zmax - R. The *VIRTUAL* vertex that
        # _fillet_polyline rounds off is ABOVE that point by:
        #       t = R*tan(135/2) = 2.41421356 R.
        # Thus root B: Z = (zmax-R) + t, NOT zmax - 60mm.
        # Tip after 135 deg turn points down-right at alpha=180-135=45 deg:
        #       delta_Y = (t + L_tail) sin(alpha)
        #       delta_Z = -(t + L_tail) cos(alpha)
        # The arc itself is fitted by _fillet_polyline; these equations put
        # its tangent EXACTLY at the upper-left corner's vertical tangent.
        alpha=math.radians(180.0-STIRRUP_HOOK_DEG)
        dy=(t+tail)*math.sin(alpha)
        dz=(t+tail)*math.cos(alpha)
        vertical_tangent_z=zmax-r
        root_b_z=vertical_tangent_z+t
        top_y=ymin+r-t+0.0008

        # A and B have overlapping projections near the re-entrant corner.
        # Stagger the two short hook bends slightly along beam X so swept
        # steel TUBES do not physically occupy the same 3-D space. This is
        # DISPLAY / BIM geometry only: verify fabrication as a planar bar
        # before issuing a construction/shop detail.
        shift=d/2+0.0006 # nominal 1.2mm free gap between opposite strands
        xA=-shift
        xB=+shift

        # A hook: actual top tangency at y ~= ymin+r, as before. Keep the
        # 135-degree leg at a constant X across the bend.
        first=V(xA,top_y+dy,zmax-dz)
        root_a=V(xA,top_y,zmax)
        # Return to nominal X in a long nearly-straight length of the top run.
        top_flat_start=min(ymax-0.070, top_y+2.0*t+0.010)
        top_flat_end=min(ymax-2.0*r-0.004,top_flat_start+0.055)
        if top_flat_end<=top_flat_start+0.025:
            raise ValueError('Insufficient width for 135-degree top-hook axial transition')

        # B hook: the true bend tangency on the LEFT side is at zmax-R.
        # The stagger transition occurs lower down along the straight side,
        # so the actual B bend remains 135 degrees in its own plane.
        left_x_begin=zmin+max(0.065,min(0.13,H*0.23))
        left_x_end=min(zmax-r-t-0.015, left_x_begin+0.095)
        if left_x_end <= left_x_begin+0.025:
            raise ValueError('Insufficient height for 135-degree side-hook axial transition')
        last=V(xB,ymin+dy,root_b_z-dz)
        path=[
            first,root_a,
            V(xA,top_flat_start,zmax),
            V(0,top_flat_end,zmax),
            V(0,ymax,zmax),V(0,ymax,zmin),V(0,ymin,zmin),
            V(0,ymin,left_x_begin),
            V(xB,ymin,left_x_end),
            V(xB,ymin,root_b_z),
            last,
        ]
        # A 135-degree hook's first curve must be near the correct outside
        # top-left tangent. B straight tail cannot be measured from the
        # imaginary vertex: actual sweep checks its terminal segment later.
        if not top_y+t<ymax-0.001:
            raise ValueError('135 hook A lacks transverse space')
        if vertical_tangent_z<=left_x_end+0.010:
            raise ValueError('135 hook B lacks straight side tangency length')
        if FIRST_LEFT_M < COVER + shift + d/2 -0.0001 or FIRST_RIGHT_M < COVER + shift + d/2 -0.0001:
            raise ValueError('First stirrup offset too small for 3-D hook staggering; increase left/right first offset')
    else:
        # 90-degree HOOKS: RESTORE the early v0.5 single-corner layout.
        # Both 90-degree bends occur at the UPPER-LEFT corner, not near the
        # centre of the top bar. Return A ends DOWN the left side and Return B
        # ends RIGHT along the top; neither is a U with two vertical legs.
        # We use the same small X stagger as the accepted 135-degree branch
        # to keep the overlapping 3D tube projections from self-intersecting.
        # The 135-degree branch above is intentionally untouched.
        shift=d/2+0.0006
        xA=-shift
        xB=+shift
        # Ninety-degree bend: tangent setback t=R*tan(90/2)=R.  Explicit
        # centreline endpoints guarantee a STRAIGHT 90 mm after the curve.
        t90=r*math.tan(math.pi/4.0)
        first=V(xA,ymin,zmax-t90-tail)           # Return A: vertical DOWN
        root_a=V(xA,ymin,zmax)                   # upper-left virtual corner
        last=V(xB,ymin+t90+tail,zmax)            # Return B: horizontal RIGHT
        root_b=V(xB,ymin,zmax)

        # Avoid the end of Return B overlapping the X transition of the top
        # run; let A remain at xA until just beyond B's endpoint.
        top_flat_start=last.y()+max(0.0045,0.45*d)
        top_flat_end=top_flat_start+max(0.021,2.25*d)
        top_limit=ymax-2*r-0.004
        if top_flat_end>top_limit:
            raise ValueError(
                '90-degree top hook cannot fit: widen the beam or shorten '
                'the tail (only if design standards permit).')

        # B keeps its X plane on the upper part of the LEFT vertical side.
        # Change X well BELOW the A vertical tail so the pieces stay apart.
        left_x_begin=zmin+max(0.065,min(0.13,H*0.23))
        left_x_end=min(zmax-t90-tail-0.022,left_x_begin+0.095)
        if left_x_end<=left_x_begin+0.025:
            raise ValueError('90-degree left-side transition does not fit')
        path=[
            first,root_a,
            V(xA,top_flat_start,zmax),
            V(0,top_flat_end,zmax),
            V(0,ymax,zmax),V(0,ymax,zmin),V(0,ymin,zmin),
            V(0,ymin,left_x_begin),
            V(xB,ymin,left_x_end),
            root_b,last,
        ]
        if FIRST_LEFT_M < COVER+shift+d/2-0.0001 or FIRST_RIGHT_M < COVER+shift+d/2-0.0001:
            raise ValueError('First stirrup offset too small for 90-degree hook stagger')

    # Evaluate the post-fillet VERTICES: the virtual B root may sit above
    # zmax, but it is removed by rounding; the actual steel must stay within.
    bent=_fillet_polyline(path,r,CORNER_STEPS)
    if STIRRUP_HOOK_DEG==135:
        if not (first.y()>top_y and first.z()<zmax and last.y()>ymin and last.z()<root_b_z):
            raise ValueError('135 hook returns must point DOWN+INWARD')
        actual_y_min=min(p.y() for p in bent)
        actual_z_max=max(p.z() for p in bent)
        if actual_y_min<ymin-0.0002 or actual_z_max>zmax+0.0002:
            raise ValueError('135 hook bend protrudes outside concrete cover')
        # The B hook is not allowed to intersect the A hook as a 3D tube.
        # This is a focused check on the two end portions, including curves.
        # Full clashes with longitudinal bars are still checked separately.
        n_end=CORNER_STEPS+3
        a=bent[:n_end]
        b=bent[-n_end:]
        min_gap=_minimum_polyline_distance_3d(a,b)
        if min_gap < d+0.0004:
            raise ValueError('135 hooks collide at corner: clearance {:.2f}mm'.format((min_gap-d)*1000))
    if STIRRUP_HOOK_DEG==90:
        # Real 90-degree hooks must stay at the UPPER-LEFT corner, with
        # orthogonal free tails (one on left face, one on top face).
        if abs(first.y()-ymin)>1e-7 or abs(last.z()-zmax)>1e-7:
            raise ValueError('90-degree hook returns misplaced away from corner')
        if not (first.z()<zmax-r and last.y()>ymin+r):
            raise ValueError('90-degree hook free tails are not orthogonal')
        # Compare the two independent curved ends in FULL 3D (not their
        # coincident 2D end-view projection).
        n_end=CORNER_STEPS+3
        a=bent[:n_end]
        b=bent[-n_end:]
        min_gap=_minimum_polyline_distance_3d(a,b)
        if min_gap < d+0.0004:
            raise ValueError('90-degree hook ends collide: gap {:.2f}mm'.format((min_gap-d)*1000))
    angle_first=hook_direction_angle(path[:3])
    angle_last=hook_direction_angle(path[-3:])
    if max(abs(angle_first-STIRRUP_HOOK_DEG),
           abs(angle_last-STIRRUP_HOOK_DEG))>0.5:
        raise ValueError(f'Incorrect stirrup hook turn: {angle_first:.1f}/{angle_last:.1f}deg')

    straight_start=(bent[1]-bent[0]).length()
    straight_end=(bent[-1]-bent[-2]).length()
    if min(straight_start,straight_end)<tail-0.001:
        raise ValueError('Hook straight extension shorter than requested AFTER circular bend')
    # Third value is the legacy output-translation value, kept at zero.
    # The short hook bends already carry their own local X stagger.
    return path,r,0.0

def make_stirrup_prototype():
    path,r,shift=stirrup_shape_vertices()
    m,length=make_rebar_mesh(path,db_m(STIRRUP_DB_MM),r,(0.85,0.74,0.30),closed=False)
    return m,length,shift


def get_span_tie_config(span_number):
    """Resolve zone parameters per span. Keys not overridden inherit defaults."""
    default = {
        'left_zone_m': LEFT_ZONE_M, 'left_spacing_m': LEFT_SPACING_M,
        'mid_spacing_m': MID_SPACING_M,
        'right_zone_m': RIGHT_ZONE_M, 'right_spacing_m': RIGHT_SPACING_M,
        'first_left_m': FIRST_LEFT_M, 'first_right_m': FIRST_RIGHT_M,
    }
    overrides=SPAN_TIE_OVERRIDES.get(span_number,{})
    if not isinstance(overrides,dict) or set(overrides)-set(default):
        raise ValueError(f"Span {span_number}: unrecognized tie-zone keys")
    result={**default,**overrides}
    return {k:float(v) for k,v in result.items()}


def span_stirrups(i, x0, x1):
    """Place stirrups between SUPPORT FACES, not support centre lines.

    Three independently configurable zones per span, with maximum spacing
    enforced in each zone and exact shared boundary stations de-duplicated.
    The finite column width is geometric context only: no beam-column joint
    rebar design is inferred by this module.
    """
    cfg=get_span_tie_config(i)
    face_left=x0+SUPPORT_WIDTH_M/2
    face_right=x1-SUPPORT_WIDTH_M/2
    first=face_left+cfg['first_left_m']
    last=face_right-cfg['first_right_m']
    if not first < last:
        raise ValueError(f'Span {i}: tie start and end cross each other')
    usable=last-first
    len_l=cfg['left_zone_m']; len_r=cfg['right_zone_m']
    if len_l+len_r<=usable:
        a=first+len_l
        b=last-len_r
    else:
        a=first+usable*len_l/(len_l+len_r)
        b=a
    zones=[('left',first,a,cfg['left_spacing_m']),
           ('middle',a,b,cfg['mid_spacing_m']),
           ('right',b,last,cfg['right_spacing_m'])]
    stations=[]
    for label,lo,hi,maxspacing in zones:
        if hi-lo<1e-9:
            continue
        pieces=max(1,math.ceil((hi-lo)/maxspacing-1e-10))
        for j in range(pieces+1):
            x=lo+(hi-lo)*j/pieces
            if stations and x-stations[-1]['x'] < 1e-7:
                if label not in stations[-1]['zones']:
                    stations[-1]['zones'].append(label)
                continue
            stations.append({'x':x,'zones':[label]})
    if len(stations)<2:
        raise ValueError(f'Span {i}: insufficient stirrup stations')
    if abs(stations[0]['x']-first)>1e-7 or abs(stations[-1]['x']-last)>1e-7:
        raise ValueError(f'Span {i}: first/last tie station incorrect')
    for a,b in zip(stations,stations[1:]):
        mid=(a['x']+b['x'])/2
        allowed=[maxspacing for lab,lo,hi,maxspacing in zones
                 if lo<=mid<=hi and hi-lo>1e-9]
        if not allowed or b['x']-a['x'] > min(allowed)+1e-7:
            raise ValueError(f'Span {i}: tie spacing exceeded')
    return stations


def volume_bounds(mesh_obj):
    if not mesh_obj.vertices:
        raise ValueError("Sweep created empty mesh")
    return tuple((min(getattr(v.position,dim)() for v in mesh_obj.vertices),
                  max(getattr(v.position,dim)() for v in mesh_obj.vertices))
                 for dim in ('x','y','z'))


def check_tie_mesh_envelope(proto, shift):
    """Inspect generated sweep vertices, not only schematic control points.

    Enforces cover on all visible tie surfaces in y/z and the x offset
    allowance for the FIRST and LAST stirrup of each span.
    """
    d=db_m(STIRRUP_DB_MM)
    xbounds,ybounds,zbounds=volume_bounds(proto)
    tol=0.0006  # tessellation/float tolerance (0.6 mm)
    violations=[]
    for low,high,limitlow,limithi,axis in [
        (ybounds[0],ybounds[1],-B/2+COVER,B/2-COVER,'Y'),
        (zbounds[0],zbounds[1],COVER,H-COVER,'Z')]:
        if low < limitlow-tol or high > limithi+tol:
            violations.append(f"{axis}: [{low*1000:.1f},{high*1000:.1f}] mm; cover region [{limitlow*1000:.1f},{limithi*1000:.1f}]")
    # no portion of a stirrup near the external span ends penetrates beam end
    minimum_offset=max(abs(xbounds[0]),abs(xbounds[1]))
    if FIRST_LEFT_M-minimum_offset < COVER-tol or FIRST_RIGHT_M-minimum_offset<COVER-tol:
        violations.append("First stirrup offset too close to beam end for staggered 135/90 hook legs; increase left/right offsets")
    if violations:
        raise ValueError("STIRRUP ENVELOPE VIOLATION: "+"; ".join(violations))
    return (xbounds,ybounds,zbounds)


def make_longitudinal(x0,x1,db_mm,z,hook_dir,color,include_end_hooks=True):
    """Main bars continuous through EVERY support; end hooks only at extremes."""
    d=db_m(db_mm)
    hook_len=min(max(12*d,0.12),0.35*H)
    bend_r=max(4*d,0.04)
    if not include_end_hooks:
        pts=[V(x0,0,z),V(x1,0,z)]
        return make_rebar_mesh(pts,d,0,color),0.,0.
    # correct main end hook orientation: from first inward leg, along run,
    # then into last hook at right beam end.
    pts=[V(x0,0,z+hook_dir*hook_len),V(x0,0,z),
         V(x1,0,z),V(x1,0,z+hook_dir*hook_len)]
    return make_rebar_mesh(pts,d,bend_r,color),hook_len,bend_r


def check_main_and_extra_levels():
    ds=db_m(STIRRUP_DB_MM)
    dt=db_m(TOP_DB_MM)
    db=db_m(BOTTOM_DB_MM)
    ztop=H-COVER-ds-dt/2
    zbot=COVER+ds+db/2
    if ztop-zbot<=0.05:
        raise ValueError("Not enough interior beam depth for top/bottom main bars")
    z_extra_top=ztop-dt/2-db_m(SPECIAL_TOP_DB_MM)/2-SPECIAL_BAR_CLEAR_M
    z_extra_bot=zbot+db/2+db_m(SPECIAL_BOTTOM_DB_MM)/2+SPECIAL_BAR_CLEAR_M
    if SPECIAL_TOP_COUNT and z_extra_top - db_m(SPECIAL_TOP_DB_MM)/2 <= COVER+ds:
        raise ValueError("Extra top bars violate concrete cover / placement")
    if SPECIAL_BOTTOM_COUNT and z_extra_bot+db_m(SPECIAL_BOTTOM_DB_MM)/2 >=H-COVER-ds:
        raise ValueError("Extra bottom bars violate concrete cover / placement")
    if SPECIAL_TOP_COUNT and SPECIAL_BOTTOM_COUNT:
        minsep=(db_m(SPECIAL_TOP_DB_MM)+db_m(SPECIAL_BOTTOM_DB_MM))/2 +0.025
        if z_extra_top-z_extra_bot<minsep:
            raise ValueError("Extra top/bottom reinforcing layers conflict; increase beam depth")
    return ztop,zbot,z_extra_top,z_extra_bot

def support_reference_solid(x):
    w=SUPPORT_WIDTH_M/2
    dy=SUPPORT_DEPTH_M/2
    return solid_box(x-w,-dy,-SUPPORT_REFERENCE_HEIGHT_M,
                     x+w,dy,0,(0.47,0.52,0.57),0.24)


def make_special_bar(xa, xb, db_mm, z, direction, tail_mm, color):
    """A 90-degree end hook on BOTH ends of each special bar.

    The virtual 90-degree corner of each hook is filleted with centreline
    radius R, so an axial leg of R+tail leaves exactly `tail` of straight
    tangent after the quarter-circle.  `direction=-1` for extra TOP hooks
    down; `+1` for extra BOTTOM hooks up.
    No fabricated anchorage or steel design is implied.
    """
    d=db_m(db_mm)
    radius=SPECIAL_HOOK_RADIUS_MULTIPLIER*d
    tail=tail_mm/1000.0
    if xa<0 or xb<=xa+2*radius+0.015:
        raise ValueError('Extra bar too short to accommodate two curved 90-degree hooks')
    if direction not in (-1,1):
        raise ValueError('Extra hook direction must be up or down')
    pts=[V(xa,0,z+direction*(radius+tail)),V(xa,0,z),
         V(xb,0,z),V(xb,0,z+direction*(radius+tail))]
    bent=_fillet_polyline(pts,radius,CORNER_STEPS)
    actual_tail_a=(bent[1]-bent[0]).length()
    actual_tail_b=(bent[-1]-bent[-2]).length()
    if abs(actual_tail_a-tail)>0.001 or abs(actual_tail_b-tail)>0.001:
        raise ValueError('Extra hook fillet did not preserve requested straight-tail length')
    low=min(v.z() for v in bent)-d/2
    high=max(v.z() for v in bent)+d/2
    inside_low=COVER+db_m(STIRRUP_DB_MM)
    inside_high=H-COVER-db_m(STIRRUP_DB_MM)
    if low<inside_low-0.0005 or high>inside_high+0.0005:
        raise ValueError(
            'Extra bar hook does not fit between stirrup top/bottom: '
            f'Z [{low*1000:.1f},{high*1000:.1f}] mm vs '
            f'[{inside_low*1000:.1f},{inside_high*1000:.1f}] mm; '
            'reduce tail if permitted, choose deeper beam or revise layers')
    m,steel_length=make_rebar_mesh(pts,d,radius,color,closed=False)
    xbnds,ybnds,zbnds=volume_bounds(m)
    if (xbnds[0]<COVER-0.0007 or
            xbnds[1]>sum(SPANS_M)-COVER+0.0007):
        raise ValueError('Extra bar and its hook extend beyond beam longitudinal concrete cover')
    if zbnds[0]<COVER-0.0007 or zbnds[1]>H-COVER+0.0007:
        raise ValueError('Extra hook sweep mesh breaches concrete top/bottom cover')
    if not all(abs(v.y())<1e-10 for v in bent):
        raise ValueError('Extra hooks unexpectedly depart from vertical beam plane')
    return m, steel_length, bent, radius


def allocate_bar_to_spans(centerline):
    """Split theoretical centreline metres between SUPPORT CENTERLINES.

    This is a billing ALLOCATION, not an accurate reinforcement cross-section
    of the beam-column joint. Vertical hooks contribute to their own span.
    """
    xedges=supports_x()
    result=[0.0]*len(SPANS_M)
    for a,b in zip(centerline,centerline[1:]):
        total=(b-a).length()
        if total<1e-12:
            continue
        cuts=[0.,1.]
        delta=b.x()-a.x()
        if abs(delta)>1e-12:
            for x in xedges[1:-1]:
                t=(x-a.x())/delta
                if 1e-10<t<1-1e-10:
                    cuts.append(t)
        cuts=sorted(set(cuts))
        for ta,tb in zip(cuts,cuts[1:]):
            xm=a.x()+(ta+tb)/2*delta
            idx=min(len(SPANS_M)-1,max(0,
                 next((i for i in range(len(SPANS_M)) if xedges[i]-1e-9<=xm<=xedges[i+1]+1e-9),len(SPANS_M)-1)))
            result[idx]+=total*(tb-ta)
    if abs(sum(result)-path_length(centerline))>0.00001:
        raise ValueError('Span quantity allocation lost rebar length')
    return result


def check_extra_hook_clashes(entries):
    """Check special TOP versus special BOTTOM bar sweep centreline capsules.

    The test checks every pair likely to be spatially near, including
    coincident cut-off planes; touching/overlapping bars are rejected.
    Full clash detection across ALL BIM bars remains to be implemented.
    """
    for i,a in enumerate(entries):
        for b in entries[i+1:]:
            if {a['kind'],b['kind']}!={'extra_top','extra_bottom'}:
                continue
            if a['xmin']>b['xmax']+0.10 or b['xmin']>a['xmax']+0.10:
                continue
            required=(db_m(a['db_mm'])+db_m(b['db_mm']))/2.0+0.0005
            min_distance=_minimum_polyline_distance_3d(a['points'],b['points'])
            if min_distance<required-0.0001:
                raise ValueError(
                    f"Extra bar hooks clash: {a['name']} and {b['name']} "
                    f"(centrelines {min_distance*1000:.1f} mm, "
                    f"required {required*1000:.1f} mm). "
                    'Reduce special bottom fraction or top support reach, or revise the layout.')


def parse_span_override_rows(raw):
    """CSV lines: span,L-zone,L-spacing,Mid-spacing,R-zone,R-spacing,L-offset,R-offset (mm)."""
    keys=('left_zone_m','left_spacing_m','mid_spacing_m','right_zone_m',
          'right_spacing_m','first_left_m','first_right_m')
    result={}
    for ln,row in enumerate(raw.splitlines(),1):
        row=row.strip()
        if not row or row.startswith('#'):
            continue
        cols=[v.strip() for v in row.split(',')]
        if len(cols)!=8:
            raise ValueError(f'Override line {ln}: expected 8 comma-separated values')
        try:
            index=int(cols[0]);values=[float(x)/1000. for x in cols[1:]]
        except Exception as exc:
            raise ValueError(f'Override line {ln}: numbers required') from exc
        if index<1 or index>len(SPANS_M) or index in result or not all(math.isfinite(x) and x>0 for x in values):
            raise ValueError(f'Override line {ln}: span index invalid/duplicate or negative value')
        result[index]=dict(zip(keys,values))
    return result


# --------------------- v0.7 Geometry Verification ----------------------------
# The narrow phase tests 3D capsule-centrelines, not just 2D end views.
# Curve portions are polygonal sampled fillets (CORNER_STEPS); the actual
# rendering mesh's world AABB is independently checked for concrete cover.
# This is a geometric screen only, NOT design-code, fabrication, or FEM proof.

def _vtuple(p):
    return (float(p.x()), float(p.y()), float(p.z()))

def _tadd(a,b):
    return (a[0]+b[0],a[1]+b[1],a[2]+b[2])

def _tsub(a,b):
    return (a[0]-b[0],a[1]-b[1],a[2]-b[2])

def _tprod(a,k):
    return (a[0]*k,a[1]*k,a[2]*k)

def _tdot(a,b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def _tlength2(a):
    return _tdot(a,a)

def _bbox_point_segment_distance2(p,low,high):
    return sum(max(low[i]-p[i],0.,p[i]-high[i])**2 for i in range(3))

def _bounds_of_points(pts,r=0.0):
    return (tuple(min(p[i] for p in pts)-r for i in range(3)),
            tuple(max(p[i] for p in pts)+r for i in range(3)))

def _bbox_distance2(a,b):
    return sum(max(a[0][i]-b[1][i], b[0][i]-a[1][i], 0.)**2 for i in range(3))

def _segment_closest_3d(a0,a1,b0,b1):
    """Exact closest pair on finite 3D line segments, robust for parallels.

    A convex quadratic over [0,1]^2 minimizes at the interior stationary
    point or along one of its four edges. Checking the interior plus all
    four clamped edge minima avoids the near-parallel branch pitfalls of
    several common online segment-distance implementations.
    """
    u=_tsub(a1,a0); v=_tsub(b1,b0); w=_tsub(a0,b0)
    aa=_tdot(u,u);bb=_tdot(u,v);cc=_tdot(v,v)
    dd=_tdot(u,w);ee=_tdot(v,w)
    epsilon=1e-17
    clamp=lambda s:max(0.,min(1.,s))
    if aa<epsilon and cc<epsilon:
        return math.sqrt(_tlength2(w)),a0,b0
    candidates=[]
    if aa<epsilon:
        candidates=[(0.,clamp(ee/cc))]
    elif cc<epsilon:
        candidates=[(clamp(-dd/aa),0.)]
    else:
        candidates=[(0.,clamp(ee/cc)),(1.,clamp((ee+bb)/cc)),
                    (clamp(-dd/aa),0.),(clamp((bb-dd)/aa),1.)]
        det=aa*cc-bb*bb
        if det>1e-12*max(aa*cc,epsilon):
            si=(bb*ee-cc*dd)/det
            ti=(aa*ee-bb*dd)/det
            if 0.<=si<=1. and 0.<=ti<=1.:
                candidates.append((si,ti))
    best=1e99; pa=pb=None
    for si,ti in candidates:
        p=_tadd(a0,_tprod(u,si));q=_tadd(b0,_tprod(v,ti))
        d2=_tlength2(_tsub(p,q))
        if d2<best:best=d2;pa=p;pb=q
    return math.sqrt(best),pa,pb

def _spatial_parts(points):
    out=[]
    for a,b in zip(points,points[1:]):
        if _tlength2(_tsub(a,b))<1e-16:continue
        out.append((a,b,_bounds_of_points([a,b])))
    return out

def _capsule_pair_nearest(a,b,threshold_m):
    """Returns nearest separation and 3D witness points; AABB culls first."""
    if _bbox_distance2(a['bounds'],b['bounds'])>threshold_m**2:
        return None
    best=1e9; pts=None
    for a0,a1,ab in a['segments']:
        for b0,b1,bb in b['segments']:
            if _bbox_distance2(ab,bb) > (best if best<1e8 else threshold_m)**2:
                continue
            distance,qa,qb=_segment_closest_3d(a0,a1,b0,b1)
            if distance<best:
                best=distance;pts=(qa,qb)
                if best<1e-9:
                    break
        if best<1e-9:
            break
    return (best,pts[0],pts[1]) if pts else None

def _longitudinal_straight_clearance(a,b):
    """Closest surface clearance of overlapping long, near-X sections only.

    Do not measure the 25mm straight-bar spacing from a 90-degree end hook:
    that produced false warnings for top-vs-bottom main bars in v0.7 alpha.
    """
    def straight_segments(bar):
        for p,q,bb in bar['segments']:
            d=_tsub(q,p);ll=math.sqrt(_tlength2(d))
            if ll>0.10 and abs(d[0])/ll>0.98:
                yield (p,q,bb)
    best=None
    for a0,a1,ab in straight_segments(a):
        for b0,b1,bb in straight_segments(b):
            if min(max(a0[0],a1[0]),max(b0[0],b1[0]))-max(min(a0[0],a1[0]),min(b0[0],b1[0]))<0.01:
                continue
            distance,pa,pb=_segment_closest_3d(a0,a1,b0,b1)
            if best is None or distance<best[0]:best=(distance,pa,pb)
    return best

def _marker_mesh(color,size):
    # Lightweight regular octahedron, one prototype per severity; faces 8.
    m=Mesh()
    x0=V(size,0,0);x1=V(-size,0,0)
    y0=V(0,size,0);y1=V(0,-size,0)
    z0=V(0,0,size);z1=V(0,0,-size)
    for tri in ((z0,x0,y0),(z0,y0,x1),(z0,x1,y1),(z0,y1,x0),
                (z1,y0,x0),(z1,x1,y0),(z1,y1,x1),(z1,x0,y1)):
        coloured_face(m,tri,color)
    return m

def verify_generated_rebar(geometry,bar_meta,stirrup_stations,bar_locations,
                           x_support,tie_r,proto_cache=None):
    """Returns a detailed issue register and BBS verification, without mutation.

    `geometry` contains actual world-space filleted centrelines and original
    shared meshes; x/y/z are in metres. Failures never move design bars.
    """
    issues=[]; proto_cache={} if proto_cache is None else proto_cache
    next_number=0
    def issue(severity,rule,parts,xyz,description,measured=None,required=None,method='geometry-3D'):
        nonlocal next_number
        next_number+=1
        entry={'id':f'V{next_number:04d}','severity':severity,'rule':rule,
               'parts':list(parts),'xyz_m':[round(float(p),6) for p in xyz],
               'message':str(description),'measured_mm':None if measured is None else round(float(measured),3),
               'required_mm':None if required is None else round(float(required),3),
               'method':method}
        issues.append(entry)
        return entry
    bars=[]
    tol=VERIFY_COVER_TOL_MM/1000.
    for raw in geometry:
        pts=[_vtuple(p) for p in raw['points']]
        if len(pts)<2: raise ValueError('Verification missing bar centreline '+raw['name'])
        radius=db_m(raw['diameter_mm'])/2.
        bb=_bounds_of_points(pts,radius)
        bar={**raw,'points':pts,'segments':_spatial_parts(pts),'bounds':bb,'radius':radius}
        bars.append(bar)
        # Independent actual swept-MESH envelope where prototype exists.
        # Shared prototype bounds are computed only once and translated.
        proto=raw.get('mesh')
        if proto is not None:
            k=id(proto)
            if k not in proto_cache:
                proto_cache[k]=volume_bounds(proto)
            local=proto_cache[k]; tx,ty,tz=raw['offset']
            bb_mesh=((local[0][0]+tx,local[1][0]+ty,local[2][0]+tz),
                     (local[0][1]+tx,local[1][1]+ty,local[2][1]+tz))
        else:
            bb_mesh=bb
        for axis,(lo,hi),(allowed_lo,allowed_hi) in zip(
            ('X','Y','Z'),zip(bb_mesh[0],bb_mesh[1]),
            ((COVER,sum(SPANS_M)-COVER),(-B/2+COVER,B/2-COVER),(COVER,H-COVER))):
            gap=min(lo-allowed_lo,allowed_hi-hi)
            if gap < -tol:
                worst=(lo if lo-allowed_lo < allowed_hi-hi else hi)
                where=list((pts[len(pts)//2]));where['XYZ'.index(axis)]=worst
                issue('ERROR','COVER', [raw['name']],where,
                      f'{axis}: actual swept mesh breaches configured concrete cover',
                      gap*1000.,0.,'swept-mesh AABB')
        recorded=bar_meta[raw['name']]['length_m']
        actual=sum(math.sqrt(_tlength2(_tsub(q,p))) for p,q,_ in bar['segments'])
        if abs(actual-recorded)>0.001:
            issue('ERROR','BBS_AXIS_LENGTH',[raw['name']],pts[len(pts)//2],
                  'Model centreline length differs from BBS',
                  (actual-recorded)*1000.,0.,'polyline-axis BBS')
    # Analytic capsule nearest-pair 3D tests with segment AABB broadphase.
    # Intentional tie-main CONTACT is allowed to tolerance; material overlap
    # beyond tolerance is always an error, whatever the part categories.
    for i,a in enumerate(bars):
        for b in bars[i+1:]:
            both_long=a['kind']!='stirrup' and b['kind']!='stirrup'
            clearance_threshold=(VERIFY_MIN_LONGITUDINAL_CLEAR_MM/1000. if both_long else .001)
            threshold=clearance_threshold+a['radius']+b['radius']
            nearest=_capsule_pair_nearest(a,b,threshold)
            if nearest is None:continue
            sep,qa,qb=nearest
            clear_m=sep-a['radius']-b['radius']
            pos=_tprod(_tadd(qa,qb),.5)
            if clear_m < -VERIFY_PENETRATION_TOL_MM/1000.:
                issue('ERROR','BAR_CLASH_3D',[a['name'],b['name']],pos,
                      '3D centreline capsules penetrate; review rebar placement',
                      clear_m*1000.,0.,'3D segment/capsule')
            elif both_long:
                straight=_longitudinal_straight_clearance(a,b)
                if straight is None:continue
                d,p0,p1=straight
                straight_clear=d-a['radius']-b['radius']
                if straight_clear<VERIFY_MIN_LONGITUDINAL_CLEAR_MM/1000.-0.0003:
                    issue('WARNING','LONGITUDINAL_CLEARANCE',[a['name'],b['name']],
                          _tprod(_tadd(p0,p1),.5),
                          'Straight longitudinal sections below configured clear spacing',
                          straight_clear*1000.,VERIFY_MIN_LONGITUDINAL_CLEAR_MM,
                          '3D straight-bar segment/capsule')
    # Verify support and midspan arrangement using actual model stations.
    ties_by_span={i:[] for i in range(1,len(SPANS_M)+1)}
    for st in stirrup_stations:
        ties_by_span[st['span']].append(float(st['x_m']))
    for idx,(x0,x1) in enumerate(zip(x_support[:-1],x_support[1:]),1):
        xs=sorted(ties_by_span[idx]);cfg=get_span_tie_config(idx)
        face_l=x0+SUPPORT_WIDTH_M/2;face_r=x1-SUPPORT_WIDTH_M/2
        if len(xs)<2:
            issue('ERROR','TIE_COUNT',[],(x0,0,H/2),f'Span {idx}: fewer than two stirrups')
            continue
        for end,actual,required in [('LEFT',xs[0]-face_l,cfg['first_left_m']),
                                    ('RIGHT',face_r-xs[-1],cfg['first_right_m'])]:
            if abs(actual-required)>0.0005:
                issue('ERROR','TIE_FIRST_OFFSET',[],(xs[0] if end=='LEFT' else xs[-1],0,H/2),
                      f'Span {idx} {end}: offset from column face differs from input',
                      actual*1000.,required*1000.)
        left_end=xs[0]+cfg['left_zone_m'];right_start=xs[-1]-cfg['right_zone_m']
        if left_end>right_start:
            cross=xs[0]+(xs[-1]-xs[0])*cfg['left_zone_m']/(cfg['left_zone_m']+cfg['right_zone_m'])
            left_end=cross;right_start=cross
        for v0,v1 in zip(xs,xs[1:]):
            mid=(v0+v1)/2
            zone=('left' if mid<left_end-1e-9 else 'right' if mid>right_start+1e-9 else 'middle')
            max_s=cfg[{'left':'left_spacing_m','middle':'mid_spacing_m','right':'right_spacing_m'}[zone]]
            if v1-v0>max_s+0.0003:
                issue('ERROR','TIE_SPACING',[],(mid,0,H/2),
                      f'Span {idx} {zone}: stirrup spacing exceeds configured maximum',
                      (v1-v0)*1000.,max_s*1000.)
        if any(b-a<=1e-5 for a,b in zip(xs,xs[1:])):
            issue('ERROR','TIE_DUPLICATE',[],(xs[0],0,H/2),f'Span {idx}: coincident stirrup stations')
    # Extra reinforcement position, hook sense, and straight-tail lengths.
    extra_top=[b for b in bars if b['kind']=='extra_top']
    extra_bottom=[b for b in bars if b['kind']=='extra_bottom']
    for idx,x in enumerate(x_support,1):
        subset=[b for b in extra_top if b['support_index']==idx]
        if len(subset)!=SPECIAL_TOP_COUNT:
            issue('ERROR','EXTRA_TOP_COUNT',[],(x,0,H*.8),f'Support P{idx}: extra top bar count incorrect',len(subset),SPECIAL_TOP_COUNT)
        if 1<idx<len(x_support):
            for b in subset:
                if not (b['points'][0][0] < x-SUPPORT_WIDTH_M/2 and b['points'][-1][0]>x+SUPPORT_WIDTH_M/2):
                    issue('ERROR','EXTRA_TOP_SUPPORT',[b['name']],(x,0,H*.8),
                          f'Support P{idx}: special top must bridge both column faces')
    for idx,(x0,x1) in enumerate(zip(x_support[:-1],x_support[1:]),1):
        mid=(x0+x1)/2
        subset=[b for b in extra_bottom if b['span_index']==idx]
        if len(subset)!=SPECIAL_BOTTOM_COUNT:
            issue('ERROR','EXTRA_BOTTOM_COUNT',[],(mid,0,H*.2),f'Span S{idx}: extra bottom bar count incorrect',len(subset),SPECIAL_BOTTOM_COUNT)
        for b in subset:
            if not (b['points'][0][0]<mid<b['points'][-1][0]):
                issue('ERROR','EXTRA_BOTTOM_MIDSPAN',[b['name']],(mid,0,H*.2),
                      f'Span {idx}: special bottom does not straddle midspan')
    for b in extra_top+extra_bottom:
        dz0=b['points'][0][2]-b['points'][1][2]
        dz1=b['points'][-1][2]-b['points'][-2][2]
        expected=(-1 if b['kind']=='extra_top' else 1)
        if dz0*expected <= 0 or dz1*expected <= 0:
            issue('ERROR','EXTRA_END_HOOK_DIRECTION',[b['name']],b['points'][0],
                  'Both special-bar tails must point down (top) or up (bottom)')
        tail=bar_meta[b['name']].get('tail_straight_after_bend_mm')
        if tail is not None:
            for a0,a1 in ((b['points'][0],b['points'][1]),(b['points'][-2],b['points'][-1])):
                straight=math.sqrt(_tlength2(_tsub(a1,a0)))*1000
                if abs(straight-tail)>1.1:
                    issue('ERROR','EXTRA_TAIL_LENGTH',[b['name']],a0,
                          'Special-bar straight tail differs from configured value',straight,tail)
    for b in bars:
        info=bar_meta[b['name']]
        nominal_bend=(stirrup_bend_radius()*1000 if b['kind']=='stirrup' else
                      (float(info.get('bend_radius_centerline_mm')) if info.get('bend_radius_centerline_mm') is not None else
                       float(info.get('bend_radius_m',0.))*1000))
        if not nominal_bend or nominal_bend<=0:
            issue('ERROR','BBS_RADIUS',[b['name']],b['points'][0],
                  'Missing positive centreline bend radius in BBS')
    counts={'ERROR':sum(x['severity']=='ERROR' for x in issues),
            'WARNING':sum(x['severity']=='WARNING' for x in issues)}
    return {'status':('GEOMETRY_ISSUES' if counts['ERROR'] else 'GEOMETRY_WARNINGS' if counts['WARNING'] else 'GEOMETRY_SCREENED'),
            'counts':counts,'issues':issues,'evaluated_bars':len(bars),
            'examined_pair_count':len(bars)*(len(bars)-1)//2,
            'method':'3D sampled centreline capsules + world swept-mesh AABB',
            'settings':{'minimum_side_by_side_clear_mm':VERIFY_MIN_LONGITUDINAL_CLEAR_MM,
                        'cover_tolerance_mm':VERIFY_COVER_TOL_MM,
                        'penetration_tolerance_mm':VERIFY_PENETRATION_TOL_MM},
            'not_checked':['National design-code compliance / seismic confinement',
                           'Development length, anchorage and lap design',
                           'Real factory bend allowances, machine and bend-pin validation',
                           'Actual support geometry, beam-column joint confinement',
                           'Verified planar fabrication of staggered stirrup hook model',
                           'Exact triangle-triangle BVH collision on final render meshes']}

def _build_bbs_verified_rows(bar_geom,bar_meta):
    """Shape codes are GO project IDs, NOT BS 8666 standardized shape codes."""
    result=[]
    for b in bar_geom:
        meta=bar_meta[b['name']]
        d=meta['diameter_mm']; radius=(stirrup_bend_radius()*1000 if b['kind']=='stirrup'
              else float(meta.get('bend_radius_centerline_mm',meta.get('bend_radius_m',0)*1000)))
        poly=meta['length_m']
        shape={'top':'GO-M90','bottom':'GO-M90','extra_top':'GO-ET90',
               'extra_bottom':'GO-EB90','stirrup':f'GO-ST{STIRRUP_HOOK_DEG}'}[b['kind']]
        # A curved shape's material length is the discretised centreline
        # length used to create the BIM mesh. It is NOT a workshop allowance.
        result.append({'beam':BEAM_ID,'bar':b['name'],'mark':meta['mark'],
           'shape_code_project_only':shape,'kind':b['kind'],'diameter_mm':d,
           'bend_radius_centerline_mm':round(radius,3),
           'straight_hook_tail_mm':meta.get('tail_straight_after_bend_mm',
                                      meta.get('hook_straight_extension_mm',
                                      round(meta.get('hook_length_nominal_m',0.)*1000,3))),
           'hook_angle_deg':meta['hook_deg'],
           'number_of_bent_ends':2 if b['kind']!='stirrup' else 2,
           'calculated_centerline_cut_length_mm':round(poly*1000,3),
           'theoretical_mass_kg':round(meta['weight_kg'],6),
           'kg_per_m':round(steel_kg_per_m(d),6),
           'fabrication_status':'PRELIMINARY: bend allowances and code need approval',
           'model_stirrup_nonplanar':b['kind']=='stirrup'})
    return result

def _add_verification_markers(parent,issues):
    """One nested untagged category; GPU-sharing marker mesh prototypes."""
    if not VERIFY_MARKERS or not issues:return [],None
    layer='GO | Verification Markers'
    if not any(ly.name==layer for ly in scene.layers):scene.layers.append(Layer(layer))
    proto={sev:_marker_mesh(rgb,VERIFY_MARKER_SIZE_MM/1000.)
           for sev,rgb in [('ERROR',(0.96,0.09,0.12)),('WARNING',(0.96,0.62,0.05))]}
    selected=sorted(issues,key=lambda d:(d['severity']!='ERROR',d['id']))[:VERIFY_MAX_MARKERS]
    subgroup=Group(Mesh(),name=f'{BEAM_ID} | Verification Markers')
    markers=[]
    for rec in selected:
        if rec['severity'] not in proto:continue
        x,y,z=rec['xyz_m']
        g=instanced_group(proto[rec['severity']],f'{BEAM_ID}-Issue-{rec["id"]}',None,
                           layer,x,y,z,metadata={'kind':'verification_marker','issue_id':rec['id'],
                                                'severity':rec['severity']})
        markers.append(g)
    if markers:
        subgroup.adopt(markers);subgroup.component=False
        subgroup.ext={TAG_KEY:{'kind':'verification_markers','excluded_from_ifc_boq':True}}
        parent.adopt(list(parent.children)+[subgroup])
    return markers,subgroup if markers else None

def show_go_rebar_verification_report(result):
    """Qt dialog: double-click a finding to focus the real 3D viewport.

    Does not modify the model. Use report CSV/JSON for full finding list.
    """
    try:
        from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,
            QTableWidget,QTableWidgetItem,QPushButton,QHeaderView,QMessageBox)
        from PySide6.QtCore import Qt
    except ImportError:
        print('Verification report GUI unavailable: see CSV/JSON outputs')
        return
    all_issues=result['issues']
    win=QDialog(globals().get('window'))
    win.setWindowTitle(f'GO RC Beam v0.7 | Verify {BEAM_ID} [{result["status"]}]')
    win.resize(1040,620)
    layout=QVBoxLayout(win)
    layout.addWidget(QLabel('Geometry screening only — NOT design / fabrication approval.'))
    layout.addWidget(QLabel(f'Bar count: {result["evaluated_bars"]} | '
                            f'ERROR: {result["counts"]["ERROR"]} | '
                            f'WARNING: {result["counts"]["WARNING"]} | '
                            f'Report: {len(all_issues)} findings'))
    if len(all_issues)>VERIFY_MAX_TABLE_ROWS:
        layout.addWidget(QLabel(f'Showing first {VERIFY_MAX_TABLE_ROWS}; open CSV for all findings.'))
    table=QTableWidget(min(len(all_issues),VERIFY_MAX_TABLE_ROWS),7,win)
    table.setHorizontalHeaderLabels(['ID','Level','Rule','Bar(s)','X (mm)','Measured','Explanation'])
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    for row,rec in enumerate(all_issues[:VERIFY_MAX_TABLE_ROWS]):
        val=[rec['id'],rec['severity'],rec['rule'],', '.join(rec['parts']),
             f'{rec["xyz_m"][0]*1000:.0f}',
             '' if rec['measured_mm'] is None else f'{rec["measured_mm"]:.2f} mm',
             rec['message']]
        for col,value in enumerate(val):
            item=QTableWidgetItem(str(value)); item.setToolTip(str(value))
            table.setItem(row,col,item)
    table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.Stretch)
    layout.addWidget(table)
    actions=QHBoxLayout();target=QPushButton('Locate / Zoom to selected issue',win)
    close=QPushButton('Close report',win)
    actions.addWidget(target);actions.addWidget(close);layout.addLayout(actions)
    def locate():
        row=table.currentRow()
        if row<0 or row>=min(len(all_issues),VERIFY_MAX_TABLE_ROWS):return
        p=all_issues[row]['xyz_m']
        vp=globals().get('viewport')
        if vp is None:return
        if getattr(vp,'camera',None) is not None:
            pt=V(*p);r=max(B,H)*0.65
            vp.camera.fit_to(pt-V(r,r,r),pt+V(r,r,r),margin=1.3)
            vp.update()
    target.clicked.connect(locate)
    table.cellDoubleClicked.connect(lambda row,col:locate())
    close.clicked.connect(win.accept)
    win.exec()

# ------------------------------ UI -----------------------------------------
def parameter_dialog():
    from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QSpinBox,
        QLineEdit,QLabel,QTabWidget,QWidget,QDialogButtonBox,QCheckBox,
        QComboBox,QDoubleSpinBox,QPlainTextEdit,QMessageBox)
    dialog=QDialog(globals().get('window'))
    dialog.setWindowTitle('GO RC Beam v0.7 | Verification + BBS')
    dialog.setMinimumSize(535,575)
    base=QVBoxLayout(dialog)
    info=QLabel('Units: mm for dimensions and spacing. Span lengths = centre-to-centre of supports.')
    info.setWordWrap(True)
    base.addWidget(info)
    tabs=QTabWidget(dialog)
    base.addWidget(tabs)
    widgets={}
    def tab(name):
        page=QWidget(dialog)
        form=QFormLayout(page)
        form.setSpacing(9)
        tabs.addTab(page,name)
        return form
    def spin(layout,label,key,scale=1,low=0,high=30000,step=5):
        w=QSpinBox(dialog)
        w.setRange(low,high)
        w.setSingleStep(step)
        w.setValue(int(round(globals()[key]*scale)))
        layout.addRow(label,w)
        widgets[key]=(w,scale)
    def fraction(layout,label,key):
        w=QDoubleSpinBox(dialog)
        w.setRange(0.05,0.90)
        w.setDecimals(2)
        w.setSingleStep(0.05)
        w.setValue(globals()[key])
        layout.addRow(label,w)
        widgets[key]=(w,1)
    ge=tab('Beam & Spans')
    beam_id=QLineEdit(BEAM_ID,dialog)
    ge.addRow('Beam ID',beam_id)
    spans=QPlainTextEdit(dialog)
    spans.setFixedHeight(72)
    spans.setPlainText(', '.join(str(int(round(s*1000))) for s in SPANS_M))
    spans.setPlaceholderText('Example: 4000, 3500, 4500')
    ge.addRow('Spans (mm; commas)',spans)
    spin(ge,'Beam width (mm)','B',1000,150,2000,25)
    spin(ge,'Beam depth (mm)','H',1000,200,2500,25)
    spin(ge,'Cover to ties (mm)','COVER',1000,20,100,5)
    spin(ge,'Main bar end offset (mm)','END_COVER',1000,30,300,5)
    spin(ge,'Plywood (mm)','PLYWOOD_THICKNESS',1000,9,40,1)
    spin(ge,'Support width (mm, along beam)','SUPPORT_WIDTH_M',1000,150,1500,25)
    spin(ge,'Support depth (mm, across beam)','SUPPORT_DEPTH_M',1000,150,1500,25)
    spin(ge,'Support reference height (mm)','SUPPORT_REFERENCE_HEIGHT_M',1000,200,5000,100)
    main=tab('Longitudinal Bars')
    spin(main,'Top main - count','TOP_COUNT',1,2,12,1)
    spin(main,'Top main - DB (mm)','TOP_DB_MM',1,6,40,1)
    spin(main,'Bottom main - count','BOTTOM_COUNT',1,2,12,1)
    spin(main,'Bottom main - DB (mm)','BOTTOM_DB_MM',1,6,40,1)
    main.addRow(QLabel('Main bars are continuous through internal supports;\n90-degree end bends appear only at the two outermost ends.'))
    st=tab('Tie 90° / 135°')
    spin(st,'Tie diameter (mm)','STIRRUP_DB_MM',1,6,25,1)
    combo=QComboBox(dialog)
    combo.addItems(['135° hook','90° hook'])
    combo.setCurrentIndex(0 if STIRRUP_HOOK_DEG==135 else 1)
    st.addRow('End-hook bend',combo)
    st.addRow(QLabel('135 deg: both diagonal returns at upper-left (unchanged).'))
    st.addRow(QLabel('90 deg: A vertical DOWN left; B horizontal RIGHT at upper-left.'))
    spin(st,'Straight tail AFTER bend (mm)','STIRRUP_HOOK_TAIL_MM',1,40,300,5)
    spin(st,'First from LEFT (mm)','FIRST_LEFT_M',1000,35,300,5)
    spin(st,'First from RIGHT (mm)','FIRST_RIGHT_M',1000,35,300,5)
    spin(st,'LEFT dense zone (mm)','LEFT_ZONE_M',1000,100,8000,50)
    spin(st,'CENTRE max spacing (mm)','MID_SPACING_M',1000,50,500,25)
    spin(st,'RIGHT dense zone (mm)','RIGHT_ZONE_M',1000,100,8000,50)
    spin(st,'LEFT max spacing (mm)','LEFT_SPACING_M',1000,50,500,25)
    spin(st,'RIGHT max spacing (mm)','RIGHT_SPACING_M',1000,50,500,25)
    sp=tab('Extra Reinforcement')
    spin(sp,'Extra TOP - count / support','SPECIAL_TOP_COUNT',1,0,8,1)
    spin(sp,'Extra TOP - DB (mm)','SPECIAL_TOP_DB_MM',1,6,40,1)
    fraction(sp,'Top extra: fraction each side','SPECIAL_TOP_FRACTION')
    spin(sp,'Extra BOTTOM - count / span','SPECIAL_BOTTOM_COUNT',1,0,8,1)
    spin(sp,'Extra BOTTOM - DB (mm)','SPECIAL_BOTTOM_DB_MM',1,6,40,1)
    fraction(sp,'Bottom extra: fraction/span','SPECIAL_BOTTOM_FRACTION')
    spin(sp,'Extra row CLEAR (mm)','SPECIAL_BAR_CLEAR_M',1000,15,70,5)
    spin(sp,'Extra TOP hook straight tail (mm)','SPECIAL_TOP_HOOK_TAIL_MM',1,40,250,5)
    spin(sp,'Extra BOTTOM hook straight tail (mm)','SPECIAL_BOTTOM_HOOK_TAIL_MM',1,40,250,5)
    spin(sp,'Special hook R/db multiplier','SPECIAL_HOOK_RADIUS_MULTIPLIER',1,2,12,1)
    sp.addRow(QLabel('TOP extra bars: 90° hooks DOWN at BOTH ends.\n'
                     'BOTTOM extra bars: 90° hooks UP at BOTH ends.\n'
                     'Straight tail measured AFTER bend; reinforcement anchorage design pending.'))
    oz=tab('Span-by-Span Stirrups')
    zones_hint=QLabel('Optional overrides: 8 numbers per line (mm)\n'
                     'span, left-zone, left-spacing, middle-spacing, right-zone, right-spacing, left-offset, right-offset\n'
                     'Example: 2, 650, 100, 125, 750, 100, 50, 50')
    zones_hint.setWordWrap(True)
    oz.addRow(zones_hint)
    tie_overrides=QPlainTextEdit(dialog)
    tie_overrides.setPlaceholderText('Blank = global settings for every span; one line per overridden span')
    tie_overrides.setPlainText('\n'.join(
        ', '.join([str(index)]+[str(int(round(params.get(key,get_span_tie_config(index)[key])*1000)))
                    for key in ('left_zone_m','left_spacing_m','mid_spacing_m',
                                'right_zone_m','right_spacing_m','first_left_m','first_right_m')])
        for index,params in sorted(SPAN_TIE_OVERRIDES.items())))
    oz.addRow(tie_overrides)
    vf=tab('Verification')
    spin(vf,'Minimum straight-bar CLEAR (mm)','VERIFY_MIN_LONGITUDINAL_CLEAR_MM',1,0,100,5)
    for desc,key in [('Cover screen tolerance (mm)','VERIFY_COVER_TOL_MM'),
                     ('Penetration tolerance (mm)','VERIFY_PENETRATION_TOL_MM')]:
        w=QDoubleSpinBox(dialog);w.setRange(0.0,5.0);w.setDecimals(2)
        w.setSingleStep(0.25);w.setValue(globals()[key]);vf.addRow(desc,w)
        widgets[key]=(w,1)
    vf.addRow(QLabel('3D capsule clearance + actual swept-mesh AABB.\n'
                    'Geometry screen only; not structural design acceptance.'))
    marker_switch=QCheckBox('Place color-coded issue markers in beam assembly',dialog)
    marker_switch.setChecked(VERIFY_MARKERS);vf.addRow(marker_switch)
    report_switch=QCheckBox('Show verification table with Locate / Zoom',dialog)
    report_switch.setChecked(VERIFY_SHOW_REPORT);vf.addRow(report_switch)
    out=tab('Output')
    marks=QCheckBox('Show model callout labels (can overcrowd the view)',dialog)
    marks.setChecked(SHOW_MARK_LABELS)
    out.addRow(marks)
    support_boxes=QCheckBox('Show support-column reference solids (not included in IFC/BOQ)',dialog)
    support_boxes.setChecked(SHOW_SUPPORT_MARKERS)
    out.addRow(support_boxes)
    ifc=QCheckBox('Write IFC4 + BOQ + BBS + metadata',dialog)
    ifc.setChecked(WRITE_IFC)
    out.addRow(ifc)
    out.addRow(QLabel('Model saved through IngeTrazo File > Save as .igz.'))
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|
                             QDialogButtonBox.StandardButton.Cancel,dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    base.addWidget(buttons)
    if dialog.exec()!=QDialog.DialogCode.Accepted:
        print('GO RC Beam v0.7.0: canceled')
        return False
    bid=beam_id.text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',bid):
        raise ValueError('Invalid Beam ID')
    raw=spans.toPlainText().strip().replace(';',',').replace('\\n',',')
    try:
        parsed=[float(v.strip())/1000 for v in raw.split(',') if v.strip()]
    except Exception:
        raise ValueError('Span lengths must be numbers in mm, comma-separated')
    if not parsed:
        raise ValueError('Enter at least one span')
    globals()['BEAM_ID']=bid
    globals()['SPANS_M']=parsed
    for key,(w,scale) in widgets.items():
        globals()[key]=w.value()/scale if scale!=1 else w.value()
    globals()['STIRRUP_HOOK_DEG']=135 if combo.currentIndex()==0 else 90
    globals()['SHOW_MARK_LABELS']=bool(marks.isChecked())
    globals()['SHOW_SUPPORT_MARKERS']=bool(support_boxes.isChecked())
    globals()['SPAN_TIE_OVERRIDES']=parse_span_override_rows(tie_overrides.toPlainText())
    globals()['WRITE_IFC']=bool(ifc.isChecked())
    globals()['VERIFY_MARKERS']=bool(marker_switch.isChecked())
    globals()['VERIFY_SHOW_REPORT']=bool(report_switch.isChecked())
    return True

# ------------------------------- Model --------------------------------------
def build_model():
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
    verification=verify_generated_rebar(bar_geom,bar_meta,stirrup_stations,bar_locations,
                                        x_support,tie_r)
    verification_markers,verification_category=_add_verification_markers(parent,verification['issues'])
    parent.ext={TAG_KEY:{'beam_id':BEAM_ID,'kind':'assembly',
        'spans_m':SPANS_M,'hook_angle_deg':STIRRUP_HOOK_DEG,
        'support_width_m':SUPPORT_WIDTH_M,'support_reference_only':True,
        'parts':len(items),'categories':[k.name for k in kids]}}
    scene.groups.append(parent)
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


if not SHOW_PARAMETER_DIALOG or parameter_dialog():
    build_model()
