"""Viewport performance diagnostics and reversible fast-shaded mode.

Uses documented IngeTrazo Style API. Never edits engineering geometry, IFC
metadata, bar centrelines or GO BBS, and never modifies viewport internals.
Full GPU timings require INGETRAZO_PERF=1 and real Windows/OpenGL session.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

@dataclass(frozen=True)
class SceneComplexity:
    top_level_groups: int
    placements: int
    unique_meshes: int
    faces_per_prototype: int
    placed_faces: int
    edges_per_prototype: int
    placed_edges: int
    prototypes_used_more_than_once: int
    largest_prototypes: tuple

    @property
    def face_amplification(self):
        return round(self.placed_faces/max(self.faces_per_prototype,1),2)


def complexity_report(scene):
    """Counts Python geometry but NEVER bakes instances or rebuilds meshes.

    `placed_faces` approximates repeated GPU work but is NOT measured GPU cost.
    No call to `world_mesh()` or actual OpenGL.
    """
    from core.group import iter_placements
    by_id={}
    placements=0
    for root in scene.groups:
        for obj,_world in iter_placements(root):
            mesh=getattr(obj,'mesh',None)
            if mesh is None:
                continue
            placements+=1
            if not mesh.faces and not mesh.edges:
                continue  # no GPU draw data in an empty category/parent
            mid=id(mesh)
            if mid not in by_id:
                by_id[mid]={'name':getattr(obj,'name','') or '(unnamed)',
                            'faces':len(mesh.faces),'edges':len(mesh.edges),
                            'instances':0,'mesh':mesh}
            by_id[mid]['instances']+=1
    rows=list(by_id.values())
    # Do not retain meshes after return; only return scalar summaries.
    high=sorted(rows,key=lambda item: item['faces']*item['instances'],reverse=True)
    return SceneComplexity(
        top_level_groups=len(scene.groups),
        placements=placements,
        unique_meshes=len(rows),
        faces_per_prototype=sum(r['faces'] for r in rows),
        placed_faces=sum(r['faces']*r['instances'] for r in rows),
        edges_per_prototype=sum(r['edges'] for r in rows),
        placed_edges=sum(r['edges']*r['instances'] for r in rows),
        prototypes_used_more_than_once=sum(r['instances']>1 for r in rows),
        largest_prototypes=tuple((r['name'],r['faces'],r['instances']) for r in high[:6]))


def diagnostic_text(scene):
    r=complexity_report(scene)
    biggest='\n'.join(f"  {name}: {faces:,} faces x {copies}"
                     for name,faces,copies in r.largest_prototypes)
    return ("IngeTrazo / GO RC Scene Geometry Audit (NOT FPS measurement)\n"
            f"Top-level groups: {r.top_level_groups:,}\n"
            f"Nested placements: {r.placements:,}\n"
            f"Unique mesh prototypes: {r.unique_meshes:,}\n"
            f"Faces, unique meshes: {r.faces_per_prototype:,}\n"
            f"Faces, all instances: {r.placed_faces:,}\n"
            f"Edges, unique meshes: {r.edges_per_prototype:,}\n"
            f"Edges, all instances: {r.placed_edges:,}\n"
            f"Face instance amplification: {r.face_amplification:.2f}x\n"
            f"Shared prototypes: {r.prototypes_used_more_than_once:,}\n"
            f"Largest placed meshes:\n{biggest}\n\n"
            "Diagnosis: if orbit improves with Profiles/Edges OFF, outline/edge "
            "passes are a likely contributor. If not, capture real "
            "INGETRAZO_PERF=1 telemetry before changing geometry.")


def set_fast_shaded(app, enabled):
    """Reversible viewport-only Style override, no .igz/Undo mutation."""
    vp=app.viewport
    win=app.window
    if enabled:
        if getattr(vp,'plano_style',None) in ('tecnico','lineas'):
            raise RuntimeError("Switch off Composer technical/lines style first; it overrides viewport Style")
        if not getattr(win,'_go_rc_fast_shaded_active',False):
            win._go_rc_prev_override=getattr(vp,'style_override',None)
        from core.style import Style
        current=getattr(vp,'style_override',None) or getattr(app.scene,'display_style',None) or Style()
        view_style=current.copy()
        view_style.name='GO RC Fast Shaded (session only)'
        view_style.face_mode='shaded'
        view_style.edges=False
        view_style.profiles=False
        view_style.back_edges=False
        vp.style_override=view_style
        win._go_rc_fast_shaded_active=True
    else:
        if getattr(win,'_go_rc_fast_shaded_active',False):
            vp.style_override=getattr(win,'_go_rc_prev_override',None)
            win._go_rc_fast_shaded_active=False
    vp.update()
    return bool(getattr(win,'_go_rc_fast_shaded_active',False))
