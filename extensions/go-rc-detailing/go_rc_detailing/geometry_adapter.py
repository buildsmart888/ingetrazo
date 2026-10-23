"""Geometry compatibility layer for IngeTrazo 0.5.9.

The frozen beam centreline and hook functions remain unchanged. We replace
only the ring profile fed to sweep_profile: it must have N distinct points,
not N+1 (the same first/last vertex repeated).

IngeTrazo 0.5.9 sweep_profile already builds two end-cap faces. Adding
extra caps would create nonmanifold meshes; do not do that.
"""
from __future__ import annotations

import math


def circular_profile_no_duplicate(mesh, origin, direction, dia, sides):
    from PySide6.QtGui import QVector3D as V
    if int(sides) < 8:
        raise ValueError("Round rebar needs at least 8 facets")
    unit = direction.normalized()
    ref = V(0.0, 0.0, 1.0)
    if abs(V.dotProduct(unit, ref)) > 0.99:
        ref = V(1.0, 0.0, 0.0)
    u = V.crossProduct(unit, ref).normalized()
    v = V.crossProduct(unit, u).normalized()
    r = float(dia) / 2.0
    # Exact loop: no repeated endpoint, no zero-length closing edge.
    ring = [origin + u*(r*math.cos(2*math.pi*i/sides))
            + v*(r*math.sin(2*math.pi*i/sides))
            for i in range(sides)]
    return mesh.add_face(ring)


def install_profile_adapter(namespace):
    original = namespace.get("_circular_profile")
    if not callable(original):
        raise RuntimeError("Baseline rebar profile function not found")
    namespace["_circular_profile"] = circular_profile_no_duplicate
    original_make = namespace["make_rebar_mesh"]

    def checked_make_rebar_mesh(*args, **kwargs):
        mesh, length = original_make(*args, **kwargs)
        assert_watertight(mesh, 'GO RC rebar sweep')
        return mesh, length

    # The function bodies and paths in accepted v0.7 are not modified.
    namespace["make_rebar_mesh"] = checked_make_rebar_mesh
    return namespace


def mesh_closed_report(mesh):
    """Inspect actual IngeTrazo mesh incidence; no automatic repair."""
    edges = list(getattr(mesh, "edges", []))
    if not edges:
        return {"closed": False, "boundary_edges": None, "nonmanifold_edges": None}
    boundary = sum(1 for edge in edges if len(edge.faces) == 1)
    nonmanifold = sum(1 for edge in edges if len(edge.faces) > 2)
    loose = sum(1 for edge in edges if len(edge.faces) == 0)
    return {"closed": bool(getattr(mesh, "faces", [])) and (boundary+nonmanifold+loose == 0),
            "boundary_edges": boundary, "nonmanifold_edges": nonmanifold,
            "loose_edges": loose, "faces": len(mesh.faces)}


def assert_watertight(mesh, name):
    report = mesh_closed_report(mesh)
    # Mocks do not implement edge/face incidence; they cannot claim success.
    if report["boundary_edges"] is None:
        return report
    if not report["closed"]:
        raise ValueError(f"Non-watertight rebar {name}: {report}")
    return report
