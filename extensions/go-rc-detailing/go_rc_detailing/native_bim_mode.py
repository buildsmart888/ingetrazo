"""Explicit trade-off for IngeTrazo 0.5.9 BIM's top-level-only collector.

No monkey-patching upstream, no invisible duplicate geometry. Either leave
an assembly nested (GO BIM Browser) or publish its leaf instances as tagged
top-level groups (IngeTrazo native BIM tray and Browser IFC class column).
Geometry prototypes remain SHARED, and all transforms are composed.
"""
from __future__ import annotations


def expose_native_bim(scene, parent, prefix=None):
    """Replace a parent by each visible leaf at the top level, undoably when
    called under SnapshotImport / core.ai.run_transactional.

    The native tree container is intentionally lost in this mode; preserve
    the logical assembly identity as metadata on the leaves instead.
    """
    from PySide6.QtGui import QMatrix4x4
    from core.group import Group, iter_placements
    if prefix is None:
        prefix = parent.name.split('-RC ')[0]
    leaves = []
    tagged = 0
    for leaf, world_transform in iter_placements(parent):
        if not getattr(leaf.mesh, 'faces', None):
            continue
        clone = Group(leaf.mesh, name=leaf.name)
        clone.xform = QMatrix4x4(world_transform) if world_transform is not None else None
        clone.layer = leaf.layer
        clone.ifc = dict(leaf.ifc) if leaf.ifc else None
        clone.ext = dict(leaf.ext or {})
        clone.ext['go_rc_native_bim'] = {
            'assembly_id': prefix,
            'original_parent': parent.name,
            'ifc_class': (clone.ifc or {}).get('class', ''),
        }
        clone.component = getattr(leaf, 'component', False)
        leaves.append(clone)
        tagged += bool(clone.ifc)
    if not leaves or not tagged:
        raise ValueError('Cannot publish assembly to native BIM: no tagged leaves')
    if parent in scene.groups:
        scene.groups.remove(parent)
    scene.groups.extend(leaves)
    return {'leaves': len(leaves), 'tagged': tagged, 'assembly': parent.name}


def expose_existing_assemblies(scene):
    """Used by optional menu command to publish existing nested RC assemblies."""
    roots = [g for g in scene.groups if (getattr(g,'ext',None) or {}).get('go_rc_column', {}).get('kind') == 'assembly'
             or (getattr(g,'ext',None) or {}).get('go_rc_beam', {}).get('kind') == 'assembly'
             or '-RC Continuous Beam Assembly' in (g.name or '')]
    return [expose_native_bim(scene, root) for root in roots]
