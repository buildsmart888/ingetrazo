"""Native scene and logical-assembly publication through a stable gateway."""
from __future__ import annotations


def publish_assembly(scene, parent):
    if parent in scene.groups:
        raise ValueError("GO RC parent group already published")
    scene.groups.append(parent)
    return {"assembly": parent.name, "mode": "nested"}


def publish_native_bim(scene, parent, *, prefix):
    from ...native_bim_mode import expose_native_bim
    return expose_native_bim(scene, parent, prefix=prefix)


def make_assembly(group_cls, mesh_cls, name, children, *, properties):
    root = group_cls(mesh_cls(), name=name)
    root.adopt(children)
    root.ext = {"go_rc": properties}
    return root


def existing_column_ids(scene):
    """Recognize nested assemblies AND top-level Native BIM leaves.

    In native visibility mode all individual leaves are promoted; the former
    parent is gone, so identifying IDs only from `C1-RC ...` names silently
    allowed a duplicate C1 in v0.8.x.
    """
    ids = set()
    for group in scene.groups:
        ext = getattr(group, 'ext', None) or {}
        col = ext.get('go_rc_column') or {}
        candidate = col.get('column_id')
        if isinstance(candidate, str) and candidate:
            ids.add(candidate)
        published = ext.get('go_rc_native_bim') or {}
        if col or 'go_rc_column' in (ext or {}):
            candidate = published.get('assembly_id')
            if isinstance(candidate, str) and candidate:
                ids.add(candidate)
        name = getattr(group, 'name', '') or ''
        if '-RC ' in name and 'Column Assembly' in name:
            ids.add(name.split('-RC ',1)[0])
    return ids


def assert_unique_column_id(scene, identifier):
    if identifier in existing_column_ids(scene):
        raise ValueError('Column ID exists in this document: use a different ID')
