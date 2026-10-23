"""GO RC Dual Display v1 — one authoritative solid, one *untagged* wire view.

Designed for stock IngeTrazo 0.5.9.  No application monkey-patches and no
new BIM quantities: wires are an edge-only Mesh, batched per RC assembly,
whereas existing IFC-tagged solid leaves remain the authoritative objects.

Bar centreline *definitions* live in scene.plugin_data, and each real bar's
Group.ext points to one definition.  This deduplicates repeated stirrups,
permits exact refresh after the user moves/rotates real bars, and persists
across .igz save/open.  It does NOT reconstruct paths by approximating solid
mesh vertices.  Geometry/BBS/IFC code never reads the wire representation.
"""
from __future__ import annotations

import hashlib
import json
import math

WIRE_LAYER = 'GO_RC_REBAR_WIRE'
SOLID_LAYER = 'GO_RC_REBAR_SOLID'
DOC_KEY = 'go_rc_dual_display'
GROUP_KEY = 'go_rc_dual_display'
MODES = ('solid', 'wire', 'both')


def _document(scene):
    pdata = getattr(scene, 'plugin_data', None)
    if pdata is None:
        scene.plugin_data = {}
        pdata = scene.plugin_data
    if not isinstance(pdata, dict):
        raise TypeError('IngeTrazo scene.plugin_data must be a dict')
    record = pdata.get(DOC_KEY)
    if not isinstance(record, dict) or record.get('version') != 1:
        record = {'version': 1, 'definitions': {}}
        pdata[DOC_KEY] = record
    record.setdefault('definitions', {})
    return record


def _ensure_layers(scene):
    from core.layers import Layer
    layer_by_name = {x.name: x for x in scene.layers}
    if SOLID_LAYER not in layer_by_name:
        solid = Layer(SOLID_LAYER, visible=True)
        scene.layers.append(solid)
    else:
        solid = layer_by_name[SOLID_LAYER]
    if WIRE_LAYER not in layer_by_name:
        wire = Layer(WIRE_LAYER, visible=False)
        scene.layers.append(wire)
    else:
        wire = layer_by_name[WIRE_LAYER]
    return solid, wire


def get_mode(scene):
    layer_by_name = {x.name: x for x in getattr(scene, 'layers', [])}
    solid = layer_by_name.get(SOLID_LAYER)
    wire = layer_by_name.get(WIRE_LAYER)
    if solid is None or wire is None:
        return 'solid'
    if solid.visible and wire.visible:
        return 'both'
    if wire.visible:
        return 'wire'
    if solid.visible:
        return 'solid'
    return 'hidden'


def _coords(points):
    output = []
    for p in points:
        if hasattr(p, 'x') and callable(p.x):
            coords = (float(p.x()), float(p.y()), float(p.z()))
        else:
            coords = tuple(float(x) for x in p)
        if len(coords) != 3 or not all(math.isfinite(c) for c in coords):
            raise ValueError('Wire centreline contains invalid coordinates')
        xyz = tuple(round(c, 9) for c in coords)  # nanometre visual precision
        if not output or xyz != output[-1]:
            output.append(xyz)
    if len(output) < 2 or all(a == b for a, b in zip(output, output[1:])):
        raise ValueError('Wire centreline needs at least one segment')
    return output


def register_bar(scene, group, local_path, *, assembly_id, diameter_mm):
    """Attach only a lightweight reference to each *solid* IfcReinforcingBar.

    This does not add geometry or modify lengths. For every repeated stirrup,
    exactly one path definition is serialized per .igz document.
    """
    if (getattr(group, 'ifc', None) or {}).get('class') != 'IfcReinforcingBar':
        raise ValueError('Dual display is only for authoritative solid IFC reinforcing bars')
    diameter = float(diameter_mm)
    if not math.isfinite(diameter) or diameter <= 0:
        raise ValueError('Invalid reinforcement diameter')
    if not isinstance(assembly_id, str) or not assembly_id:
        raise ValueError('Missing assembly identifier')
    pts = _coords(local_path)
    payload = {'points': pts, 'diameter_mm': diameter}
    signature = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    key = 'path-' + hashlib.sha256(signature.encode('utf-8')).hexdigest()[:32]
    registry = _document(scene)['definitions']
    if key not in registry:
        registry[key] = payload
    _ensure_layers(scene)
    ext = dict(getattr(group, 'ext', None) or {})
    existing = ext.get(GROUP_KEY) or {}
    original_layer = existing.get('original_layer', getattr(group, 'layer', None))
    ext[GROUP_KEY] = {'version': 1, 'role': 'solid', 'assembly_id': assembly_id,
                      'definition': key, 'original_layer': original_layer}
    group.ext = ext
    group.layer = SOLID_LAYER
    return key


def register_beam(scene, state, assembly_id):
    """Use Phase2's accepted swept centreline, not a guessed mesh skeleton."""
    parts = {g.name: g for g in state.items}
    count = 0
    for row in state.bar_geom:
        g = parts.get(row['name'])
        if g is None:
            raise RuntimeError('Missing beam bar in dual display: ' + row['name'])
        if row.get('kind') == 'stirrup':
            # Reuse the exact local prototype of all placed ties: avoids
            # float cancellation when extracting long span station offsets.
            local = state.tie_path
        else:
            dx, dy, dz = (float(x) for x in row['offset'])
            local = [(float(p.x())-dx, float(p.y())-dy, float(p.z())-dz)
                     for p in row['points']]
        register_bar(scene, g, local, assembly_id=assembly_id,
                     diameter_mm=row['diameter_mm'])
        count += 1
    return count


def _wire_group(group):
    block = (getattr(group, 'ext', None) or {}).get(GROUP_KEY) or {}
    return block.get('version') == 1 and block.get('role') == 'wire'


def _mapped_path(path, transform):
    from PySide6.QtGui import QVector3D
    if transform is None:
        return [QVector3D(*p) for p in path]
    return [transform.map(QVector3D(*p)) for p in path]


def refresh_wire_overlays(scene, extra_sources=()):
    """Rebuild one edges-only group per assembly from signed local paths.

    Safe to call when the solid groups have moved or on reopening a .igz.
    The returned count is an audit, NOT an IFC/BBS/engineering quantity.
    A non-registered (older v0.10.2) bar cannot be reverse-engineered safely.
    """
    from PySide6.QtGui import QVector3D
    from core.group import Group, iter_placements
    from core.mesh import Mesh

    doc = _document(scene)
    registry = doc['definitions']
    _ensure_layers(scene)
    grouped = {}
    visited = set()
    missed = 0
    for root in list(scene.groups) + list(extra_sources):
        if _wire_group(root):
            continue
        for bar, xf in iter_placements(root):
            # extra_sources may also already belong to scene.groups.
            if id(bar) in visited:
                continue
            visited.add(id(bar))
            if (getattr(bar, 'ifc', None) or {}).get('class') != 'IfcReinforcingBar':
                continue
            ref = (getattr(bar, 'ext', None) or {}).get(GROUP_KEY) or {}
            if ref.get('role') != 'solid' or ref.get('version') != 1:
                missed += 1
                continue
            definition = registry.get(ref.get('definition'))
            if not isinstance(definition, dict):
                missed += 1
                continue
            aid = ref['assembly_id']
            grouped.setdefault(aid, []).append((definition['points'], xf))

    # Build everything successfully before replacing previously drawn wires.
    new_groups = {}
    for aid, paths in grouped.items():
        wire_mesh = Mesh()
        edges_count = 0
        for local_path, transform in paths:
            points = _mapped_path(local_path, transform)
            for a, b in zip(points, points[1:]):
                if (a-b).length() <= 1e-8:
                    continue
                wire_mesh.add_edge(a, b)
                edges_count += 1
        if not edges_count:
            continue
        wire = Group(wire_mesh, name=f'{aid}-GO_RC_Centerline_Wire')
        wire.layer = WIRE_LAYER
        wire.component = False
        wire.ifc = None
        wire.material = {'color': (0.15, 0.58, 0.85)}
        wire.ext = {GROUP_KEY: {'version': 1, 'role': 'wire', 'assembly_id': aid,
                                'bars': len(paths), 'segments': edges_count}}
        new_groups[aid] = wire

    old = {((g.ext or {}).get(GROUP_KEY) or {}).get('assembly_id'): g
           for g in scene.groups if _wire_group(g)}
    # Preserve the original wire Group uid/selection when refreshing. This
    # keeps named references stable, but replaces its Mesh in one operation.
    for aid, wire in new_groups.items():
        existing = old.pop(aid, None)
        if existing is None:
            scene.groups.append(wire)
        else:
            existing.mesh = wire.mesh
            existing.xform = None  # world coords; reset accidental wire move
            existing.layer = WIRE_LAYER
            existing.ext = wire.ext
    if old:
        selected = getattr(scene, 'selection', None)
        if selected is not None:
            for obsolete in old.values():
                selected.discard(obsolete)
        scene.groups[:] = [g for g in scene.groups if g not in old.values()]
    return {'assemblies': len(new_groups),
            'bars': sum(len(v) for v in grouped.values()),
            'edges': sum(len(g.mesh.edges) for g in new_groups.values()),
            'missing_legacy_bars': missed,
            'unique_path_definitions': len(registry)}


def set_mode(scene, mode):
    """Toggle persisted host Layers; excludes hidden solid meshes from picking.

    Display changes are document view changes, never a regeneration of
    real solid meshes, quantities or identifiers.  Only rebuild wires on
    entering wire/both (for accurate transforms after solid edits).
    """
    if mode not in MODES:
        raise ValueError('Unknown GO RC display mode: ' + str(mode))
    solid, wire = _ensure_layers(scene)
    stats = None
    if mode != 'solid':
        stats = refresh_wire_overlays(scene)
        if stats['assemblies'] == 0 and stats['missing_legacy_bars']:
            raise ValueError('No GO RC Wire data in this document. Build a NEW v0.10.3 beam/column; older objects lack stored centreline definitions.')
    new_solid = mode in ('solid', 'both')
    new_wire = mode in ('wire', 'both')
    changed = solid.visible != new_solid or wire.visible != new_wire
    solid.visible, wire.visible = new_solid, new_wire
    if changed or stats:
        # Layers are part of persisted document state: notify the renderer
        # and document dirty tracking. Do NOT invalidate the actual meshes.
        scene.version += 1
    return {'mode': mode, 'changed': changed, 'wire': stats}
