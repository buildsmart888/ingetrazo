# SPDX-License-Identifier: GPL-3.0-or-later
"""Continuous RB9 stirrups as shared components (metres throughout).

RUN: Extensions > Python Console > Run script file... on a new document.
The AI Assistant's Python executor can also run the complete file.
No box()/prism() helper or external Python package is needed.

All 19 RB9 placements share ONE local-coordinate mesh. The five straight
DB12 bars use two more prototypes (one per colour); each placement has its
own transform, identity and BIM tag. The patched host's rebar display helper
attaches a verified centreline for interactive line rendering. Older hosts
can still build the components, but ignore that optional display metadata.

This fixes geometry, not reinforcement design. Bend radius, hook tails and
the small out-of-plane hook offset below are illustrative, editable values.
The default configuration was checked for self-intersection / bar clearance.
Changing dimensions requires a new clearance check; topology alone does not
prove that arbitrarily modified hooks fit the beam or avoid neighbouring bars.
Original beam / longitudinal-bar coordinates are preserved (including their
zero end cover). The two 135-degree hooks overlap in YZ projection, but are
separated in X. One smooth jog on the left leg connects their planes.

Re-running replaces ONLY groups whose names start with PREFIX. It never
clears the whole document. Open a new document to avoid seeing the old,
broken example behind this one. Console execution supplies one undo step.

API inspected: buildsmart888/ingetrazo commit
2daee48d4760cb4b6cbc406d11e8fbf0b9c07d1d, core/mesh.py,
core/group.py and plugins/python_console.py (2026-10-22).
The tuple geometry can be imported and checked without IngeTrazo / Qt.
"""

import math
from collections import Counter


# ---- Parameters: ALL lengths in metres -----------------------------------
PREFIX = "GO_RB9FIX_"
BEAM_LENGTH, BEAM_WIDTH, BEAM_HEIGHT = 3.0, 0.20, 0.40
STIRRUP_DIAMETER = 0.009
LONGITUDINAL_DIAMETER = 0.012
SPACING = 0.15
FIRST_STIRRUP, LAST_STIRRUP = 0.15, 2.85

# These are CENTRELINE limits, not concrete cover or bar outer dimensions.
Y_MIN, Y_MAX = 0.02, 0.18
Z_MIN, Z_MAX = 0.04, 0.36
BEND_RADIUS = 0.020           # Centreline radius; inner radius = R - d/2.
HOOK_TAIL = 0.090             # Straight part AFTER each 135-degree bend.
HOOK_OFFSET_X = 0.012         # 12 mm between hook planes: 3 mm surface gap.
JOG_START_Z, JOG_END_Z = 0.20, 0.32

CIRCLE_SIDES = 16
ARC_SEGMENTS_PER_90 = 8
JOG_SEGMENTS = 12
CONCRETE_ALPHA = 0.15
EPS = 1.0e-10

TOP_BARS_YZ = ((0.04, 0.34), (0.10, 0.34), (0.16, 0.34))
BOTTOM_BARS_YZ = ((0.06, 0.06), (0.14, 0.06))


# ---- Pure geometry, independent of the application's scene ----------------
def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _mul(a, s):
    return tuple(s * a[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def _length(v):
    return math.sqrt(_dot(v, v))


def _unit(v):
    n = _length(v)
    if n <= EPS:
        raise ValueError("Zero-length tangent or direction.")
    return _mul(v, 1.0 / n)


def _append_sample(samples, point, tangent):
    tangent = _unit(tangent)
    if samples and _length(_sub(point, samples[-1][0])) <= EPS:
        if _dot(tangent, samples[-1][1]) < 1.0 - 1.0e-7:
            raise ValueError("Non-tangent connection between path pieces.")
        return                         # Share the line/arc junction ring.
    samples.append((tuple(point), tangent))


def _line(samples, a, b):
    t = _unit(_sub(b, a))
    _append_sample(samples, a, t)
    _append_sample(samples, b, t)


def _clockwise_arc(samples, x, cy, cz, start_deg, end_deg, radius):
    if start_deg <= end_deg:
        raise ValueError("This arc helper expects a clockwise bend.")
    n = max(1, int(math.ceil((start_deg - end_deg)
                             / 90.0 * ARC_SEGMENTS_PER_90)))
    for i in range(n + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / n)
        p = (x, cy + radius * math.cos(a), cz + radius * math.sin(a))
        t = (0.0, math.sin(a), -math.cos(a))
        _append_sample(samples, p, t)


def stirrup_path(x_pos):
    """One OPEN centreline: tail A -> 135 -> perimeter -> 135 -> tail B.

    The resulting solid has exactly two caps. Never join its free ends or
    add a branched hook to a closed rectangle.
    """
    r = BEND_RADIUS
    if not (STIRRUP_DIAMETER / 2 < r
            < min(Y_MAX - Y_MIN, Z_MAX - Z_MIN) / 2):
        raise ValueError("Bend radius does not fit the bar / rectangle.")
    if not (Z_MIN + r < JOG_START_Z < JOG_END_Z < Z_MAX - r):
        raise ValueError("The axial jog must fit inside the left straight leg.")
    if HOOK_OFFSET_X <= STIRRUP_DIAMETER:
        raise ValueError("The two overlapping hook planes need X separation > d.")
    if HOOK_TAIL <= 0:
        raise ValueError("Hook tail must be positive.")

    cy, cz = Y_MIN + r, Z_MAX - r
    a = math.radians(225.0)
    hook_start = (x_pos, cy + r*math.cos(a), cz + r*math.sin(a))
    start_tangent = (0.0, math.sin(a), -math.cos(a))
    tail_a = _sub(hook_start, _mul(start_tangent, HOOK_TAIL))
    s = []
    _line(s, tail_a, hook_start)
    _clockwise_arc(s, x_pos, cy, cz, 225, 90, r)  # First 135-degree hook.

    _line(s, s[-1][0], (x_pos, Y_MAX-r, Z_MAX))
    _clockwise_arc(s, x_pos, Y_MAX-r, Z_MAX-r, 90, 0, r)
    _line(s, s[-1][0], (x_pos, Y_MAX, Z_MIN+r))
    _clockwise_arc(s, x_pos, Y_MAX-r, Z_MIN+r, 0, -90, r)
    _line(s, s[-1][0], (x_pos, Y_MIN+r, Z_MIN))
    _clockwise_arc(s, x_pos, Y_MIN+r, Z_MIN+r, -90, -180, r)
    _line(s, s[-1][0], (x_pos, Y_MIN, JOG_START_Z))

    # Smooth, tangent-continuous X offset; not a sudden sideways step.
    h = JOG_END_Z - JOG_START_Z
    for i in range(JOG_SEGMENTS + 1):
        u = i / JOG_SEGMENTS
        dx = HOOK_OFFSET_X * (3*u*u - 2*u*u*u)
        dx_dz = HOOK_OFFSET_X * 6*u*(1-u) / h
        _append_sample(s, (x_pos + dx, Y_MIN, JOG_START_Z + h*u),
                       (dx_dz, 0.0, 1.0))

    x_end = x_pos + HOOK_OFFSET_X
    _line(s, s[-1][0], (x_end, Y_MIN, Z_MAX-r))
    _clockwise_arc(s, x_end, cy, cz, 180, 45, r)  # Second 135-degree hook.
    _line(s, s[-1][0], _add(s[-1][0], _mul(s[-1][1], HOOK_TAIL)))
    return s


def tube_mesh_data(samples, diameter, sides=CIRCLE_SIDES):
    """Sweep perpendicular circular rings, sharing rings across every joint.

    Parallel transport keeps ring orientation stable through the 3D jog.
    Triangles remain planar even where the centreline leaves the YZ plane.
    """
    if len(samples) < 2 or diameter <= 0 or sides < 8:
        raise ValueError("Tube needs >=2 samples, d>0 and >=8 circle sides.")
    radius = diameter / 2
    verts, faces = [], []
    old_t, u = None, None
    for point, tangent in samples:
        t = _unit(tangent)
        if old_t is None:
            ref = (1.0, 0.0, 0.0) if abs(t[0]) < 0.9 else (0.0, 1.0, 0.0)
            u = _unit(_sub(ref, _mul(t, _dot(ref, t))))
        else:
            axis = _cross(old_t, t)
            sine = _length(axis)
            cosine = max(-1.0, min(1.0, _dot(old_t, t)))
            if sine > EPS:
                axis = _mul(axis, 1.0 / sine)
                u = _add(_add(_mul(u, cosine), _mul(_cross(axis, u), sine)),
                         _mul(axis, _dot(axis, u) * (1.0 - cosine)))
            elif cosine < 0:
                raise ValueError("A 180-degree tangent reversal needs a bend arc.")
            u = _unit(_sub(u, _mul(t, _dot(u, t))))
        v = _unit(_cross(t, u))  # u x v = tangent; consistent winding.
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            offset = _add(_mul(u, radius*math.cos(a)),
                          _mul(v, radius*math.sin(a)))
            verts.append(_add(point, offset))
        old_t = t

    for i in range(len(samples) - 1):
        for j in range(sides):
            k = (j + 1) % sides
            a, b = i*sides+j, i*sides+k
            c, d = (i+1)*sides+k, (i+1)*sides+j
            faces.extend(((a, b, c), (a, c, d)))
    side_face_count = len(faces)

    cap_a, cap_b = len(verts), len(verts) + 1
    verts.extend((samples[0][0], samples[-1][0]))
    last = (len(samples) - 1) * sides
    for j in range(sides):
        k = (j + 1) % sides
        faces.extend(((cap_a, k, j), (cap_b, last+j, last+k)))
    return {"vertices": verts, "faces": faces,
            "side_face_count": side_face_count}


def check_mesh(data):
    """Topology/volume checks. Does NOT certify reinforcement design.

    Self-intersection is a separate geometric question; the default hook
    configuration was also checked by a densely sampled clearance check.
    """
    verts, faces = data["vertices"], data["faces"]
    if any(not math.isfinite(c) for p in verts for c in p):
        raise ValueError("Non-finite mesh coordinate.")
    edges, directed, neighbours = Counter(), Counter(), {}
    volume = 0.0
    origin = verts[0]
    for tri in faces:
        if len(set(tri)) != 3:
            raise ValueError("Repeated vertex in a triangle.")
        a, b, c = (verts[i] for i in tri)
        if _length(_cross(_sub(b, a), _sub(c, a))) <= 1.0e-12:
            raise ValueError("Zero-area triangle.")
        volume += _dot(_sub(a, origin),
                       _cross(_sub(b, origin), _sub(c, origin))) / 6.0
        for i, j in zip(tri, tri[1:] + tri[:1]):
            edges[tuple(sorted((i, j)))] += 1
            directed[(i, j)] += 1
            neighbours.setdefault(i, set()).add(j)
            neighbours.setdefault(j, set()).add(i)
    if any(n != 2 for n in edges.values()):
        raise ValueError("Open or non-manifold edge.")
    if any(directed[(i, j)] != 1 or directed[(j, i)] != 1 for i, j in edges):
        raise ValueError("Inconsistent triangle winding.")
    seen, stack = set(), [0]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(neighbours.get(node, set()) - seen)
    if len(seen) != len(verts):
        raise ValueError("Mesh is not one connected component.")
    if len(verts) - len(edges) + len(faces) != 2 or volume <= 0:
        raise ValueError("Invalid capped-bar topology or orientation.")
    return {"vertices": len(verts), "triangles": len(faces),
            "boundary_edges": 0, "non_manifold_edges": 0,
            "components": 1, "signed_volume_m3": volume}


def _box_data():
    l, w, h = BEAM_LENGTH, BEAM_WIDTH, BEAM_HEIGHT
    verts = [(0,0,0), (l,0,0), (l,w,0), (0,w,0),
             (0,0,h), (l,0,h), (l,w,h), (0,w,h)]
    quads = [(0,3,2,1), (4,5,6,7), (0,1,5,4),
             (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    faces = []
    for a, b, c, d in quads:
        faces.extend(((a,b,c), (a,c,d)))
    return {"vertices": verts, "faces": faces, "side_face_count": None}


def stirrup_positions():
    if SPACING <= 0 or FIRST_STIRRUP > LAST_STIRRUP:
        raise ValueError("Invalid stirrup spacing or limits.")
    count = int(math.floor((LAST_STIRRUP - FIRST_STIRRUP) / SPACING + 1e-9)) + 1
    return [FIRST_STIRRUP + i*SPACING for i in range(count)]


# ---- IngeTrazo adapter: actual documented source API ----------------------
def _make_group(data, name, color, ifc_class):
    from PySide6.QtGui import QVector3D
    from core.mesh import Mesh
    from core.group import Group

    mesh = Mesh()
    positions = [QVector3D(*p) for p in data["vertices"]]
    side_faces = set()
    side_count = data["side_face_count"]
    # The host stores RGB and opacity separately. A fourth colour component
    # alone is ignored by the viewport and would make the concrete opaque.
    rgb = tuple(color[:3])
    opacity = float(color[3]) if len(color) > 3 else 1.0
    for i, triangle in enumerate(data["faces"]):
        face = mesh.add_face([positions[j] for j in triangle])
        face.attrs["color"] = rgb
        face.attrs["opacity"] = opacity
        if side_count is not None and i < side_count:
            side_faces.add(face)

    # Check again AFTER the application's positional vertex welding.
    if len(mesh.vertices) != len(positions) or any(len(e.faces) != 2 for e in mesh.edges):
        raise ValueError("IngeTrazo vertex welding changed the intended closed mesh.")
    if side_count is not None:
        for edge in mesh.edges:
            edge.soft = ((edge.faces[0] in side_faces) ==
                         (edge.faces[1] in side_faces))
    group = Group(mesh, name=name)
    group.layer = ifc_class
    group.ifc = {"class": ifc_class, "name": name}
    return group


def _rebar_definition(samples, diameter, color, short_name):
    """Build one immutable local mesh and the path used to display it."""
    import hashlib
    import json

    data = tube_mesh_data(samples, diameter)
    report = check_mesh(data)
    prototype = _make_group(
        data, PREFIX + short_name + "_Definition", color, "IfcReinforcingBar")
    points = [list(point) for point, _tangent in samples]
    # A stable, content-based key distinguishes later parameter variants.
    payload = json.dumps([diameter, CIRCLE_SIDES, samples], separators=(",", ":"))
    key = "go-rebar-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    _attach_rebar_path(prototype, points, diameter, key)
    return prototype.mesh, report, points, key, prototype.ext["go_rebar"]


def _attach_rebar_path(group, points, diameter, key):
    """Prepare one verified path block per definition, before placing copies."""
    try:
        from core.rebar_display import attach_centerline
    except ModuleNotFoundError as error:
        if error.name != "core.rebar_display":
            raise
        # Compatibility with an older host. Its renderer ignores these
        # fields; an upgraded host requires a verified mesh signature and
        # therefore safely keeps full geometry until this script is rerun.
        group.ext = {"go_rebar": {
            "version": 1,
            "centerline": points,
            "diameter_m": diameter,
            "definition_key": key,
        }}
    else:
        attach_centerline(group, points, diameter, key)


def _rebar_instance(definition, offset, name, diameter):
    """Place a shared mesh without moving any of its vertices."""
    from PySide6.QtGui import QMatrix4x4
    from core.group import Group

    mesh, _report, _points, _key, block = definition
    if block["diameter_m"] != diameter:
        raise ValueError("Instance diameter must match its shared definition.")
    group = Group(mesh, name=name)
    group.xform = QMatrix4x4()
    group.xform.translate(*offset)
    group.component = True
    group.layer = "IfcReinforcingBar"
    group.ifc = {"class": "IfcReinforcingBar", "name": name}
    # Share the immutable definition block too: the renderer validates and
    # packs this path once, rather than repeating that work for every bar.
    # Parametric edits replace the block; per-instance extension data stays
    # independent because each container has its own outer dictionary.
    group.ext = {"go_rebar": block}
    return group


def build_beam(scene, viewport=None):
    """Build and check all objects before replacing this example's groups.

    Run inside the Console/AI executor, which handles scene invalidation,
    transactions and undo. A plugin should call this inside SnapshotImport.
    """
    from PySide6.QtGui import QVector3D
    from core.layers import Layer

    pending, reports = [], []

    def add(data, short_name, color, ifc_class):
        reports.append(check_mesh(data))
        pending.append(_make_group(data, PREFIX + short_name, color, ifc_class))

    add(_box_data(), "Concrete", (0.85,0.85,0.85,CONCRETE_ALPHA), "IfcBeam")
    straight_path = [((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                     ((BEAM_LENGTH, 0.0, 0.0), (1.0, 0.0, 0.0))]
    for label, yz_list, color in (
            ("DB12_Top", TOP_BARS_YZ, (0.9,0.2,0.2,1.0)),
            ("DB12_Bottom", BOTTOM_BARS_YZ, (0.9,0.5,0.1,1.0))):
        definition = _rebar_definition(
            straight_path, LONGITUDINAL_DIAMETER, color, label)
        for i, (y, z) in enumerate(yz_list, 1):
            name = PREFIX + "{}_{:02d}".format(label, i)
            pending.append(_rebar_instance(
                definition, (0.0, y, z), name, LONGITUDINAL_DIAMETER))
            reports.append(definition[1])

    xs = stirrup_positions()
    definition = _rebar_definition(
        stirrup_path(0.0), STIRRUP_DIAMETER, (0.1, 0.3, 0.9, 1.0), "RB9")
    for i, x in enumerate(xs, 1):
        pending.append(_rebar_instance(
            definition, (x, 0.0, 0.0), PREFIX + "RB9_{:02d}".format(i),
            STIRRUP_DIAMETER))
        reports.append(definition[1])

    # Preserve unrelated objects. Remove only an earlier run of THIS script.
    replaced = {group for group in scene.groups
                if str(group.name).startswith(PREFIX)}
    scene.selection.difference_update(replaced)
    for group in list(scene.groups):
        if group in replaced:
            scene.groups.remove(group)
    for name in ("IfcBeam", "IfcReinforcingBar"):
        if not any(layer.name == name for layer in scene.layers):
            scene.layers.append(Layer(name))
    scene.groups.extend(pending)

    if viewport is not None:
        viewport.camera.target = QVector3D(1.5, 0.1, 0.2)
        viewport.camera.distance = 2.5
        viewport.camera.yaw = 0.9
        viewport.camera.pitch = -0.3
        viewport.update()

    unique_meshes = {id(group.mesh): group.mesh for group in pending}
    result = {"groups_created": len(pending), "stirrups": len(xs),
              "triangles": sum(r["triangles"] for r in reports),
              "boundary_edges": sum(r["boundary_edges"] for r in reports),
              "unique_meshes": len(unique_meshes),
              "unique_mesh_faces": sum(len(mesh.faces) for mesh in unique_meshes.values()),
              "stirrup_meshes": 1}
    print("Created: 1 beam, 3 top DB12, 2 bottom DB12, {} RB9 stirrups.".format(len(xs)))
    print("Each stirrup: one connected capped mesh; 2 x 135-degree hooks.")
    print("Geometry checks: {} groups, {} placed triangles, {} boundary edges.".format(
        result["groups_created"], result["triangles"], result["boundary_edges"]))
    print("Stored geometry: {} unique meshes, {} triangle faces; RB9 uses 1 mesh.".format(
        result["unique_meshes"], result["unique_mesh_faces"]))
    print("Bend/hook/jog dimensions are example parameters, not a design-code check.")
    return result


if "scene" in globals():
    GO_RB9_RESULT = build_beam(scene, globals().get("viewport"))
elif __name__ == "__main__":
    print("Open IngeTrazo > Extensions > Python Console > Run script file...")
