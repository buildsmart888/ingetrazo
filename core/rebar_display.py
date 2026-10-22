# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional, verified display proxies for reinforcement component meshes.

The solid remains the document geometry. A centreline is only a drawing
cache, never a replacement for picking, quantities, undo or export.
"""
from __future__ import annotations

import hashlib
import math
import struct
import weakref


_SIGNATURES = weakref.WeakKeyDictionary()


def _point_bytes(point):
    if hasattr(point, "x"):
        point = (point.x(), point.y(), point.z())
    return struct.pack("<3f", *point)


def _loop_bytes(vertices):
    points = [_point_bytes(v.position) for v in vertices]
    if not points:
        return b""
    # Save/load may rotate a face's first vertex or reverse its winding.
    # Both describe the same surface for a display proxy.
    variants = []
    for seq in (points, list(reversed(points))):
        first = min(range(len(seq)), key=seq.__getitem__)
        variants.append(b"".join(seq[first:] + seq[:first]))
    return min(variants)


def mesh_signature(mesh) -> str:
    """Persistent shape digest, cached per mesh mutation serial.

    The canonical loops make the digest independent of insertion order and
    of native-file vertex numbering. Mesh editing must use its mutation API,
    as required by the viewport's other geometry caches too.
    """
    serial = getattr(mesh, "_mut_serial", None)
    key = (serial, len(mesh.vertices), len(mesh.edges), len(mesh.faces))
    cached = _SIGNATURES.get(mesh)
    if cached is not None and cached[0] == key:
        return cached[1]
    h = hashlib.sha256()
    h.update(struct.pack("<3Q", *key[1:]))
    for face in sorted(
        _loop_bytes(f.loop) + b"|" + b"|".join(sorted(
            _loop_bytes(hole) for hole in f.hole_loops))
        for f in mesh.faces
    ):
        h.update(struct.pack("<Q", len(face)))
        h.update(face)
    for point in sorted(_point_bytes(v.position) for v in mesh.vertices):
        h.update(point)
    digest = h.hexdigest()
    _SIGNATURES[mesh] = (key, digest)
    return digest


def attach_centerline(group, points, diameter_m: float, definition_key: str) -> None:
    """Attach a serialisable local-space proxy to an already built mesh.

    Call again after a parametric geometry rebuild. A free mesh edit leaves
    the old digest behind and the renderer safely falls back to the solid.
    """
    points = [[float(c) for c in p] for p in points]
    if (len(points) < 2 or any(len(p) != 3 for p in points)
            or not all(math.isfinite(c) for p in points for c in p)
            or not math.isfinite(diameter_m) or diameter_m <= 0):
        raise ValueError("A rebar centreline needs finite 3D points and a positive diameter.")
    block = {"version": 1, "centerline": points,
             "diameter_m": float(diameter_m), "definition_key": str(definition_key),
             "mesh_signature": mesh_signature(group.mesh)}
    group.ext = dict(getattr(group, "ext", None) or {})
    group.ext["go_rebar"] = block


class CenterlineCache:
    """Validate metadata once per block and mesh revision, without id reuse."""

    def __init__(self):
        self._meshes = weakref.WeakKeyDictionary()

    def clear(self):
        self._meshes.clear()

    def get(self, group, revision=None):
        """Return ``(proxy_key, GL_LINES bytes)`` or None for a safe fallback."""
        ext = getattr(group, "ext", None)
        block = ext.get("go_rebar") if isinstance(ext, dict) else None
        if (not isinstance(block, dict) or block.get("version") != 1
                or getattr(group, "xform", None) is None
                or getattr(group, "children", None)
                or getattr(group, "billboard", False)):
            return None
        mesh = group.mesh
        serial = (revision, getattr(mesh, "_mut_serial", None), len(mesh.vertices),
                  len(mesh.edges), len(mesh.faces))
        entry = self._meshes.get(mesh)
        if entry is None or entry[0] != serial:
            entry = (serial, {}, {})
            self._meshes[mesh] = entry
        cache = entry[1]
        signature = block.get("mesh_signature")
        if not isinstance(signature, str):
            return None
        points = block.get("centerline")
        # Metadata is replaced on rebuild, not mutated in-place. Its owning
        # block stays in the entry to prevent a recycled Python id collision.
        key = (id(block), id(points), signature)
        hit = cache.get(key)
        if hit is not None and hit[0] is block:
            return hit[1]
        result = None
        try:
            diameter = float(block["diameter_m"])
            if (not isinstance(signature, str) or signature != mesh_signature(mesh)
                    or not isinstance(points, (tuple, list)) or len(points) < 2
                    or not math.isfinite(diameter) or diameter <= 0):
                return None
            # Native reload gives each instance its own JSON dictionary.
            # Reuse packed data only after equality with the validated path,
            # never merely because two callers supplied the same name.
            definition = block.get("definition_key")
            if not isinstance(definition, str):
                return None
            canonical_key = (signature, definition, diameter)
            canonical = entry[2].get(canonical_key)
            if canonical is not None and points == canonical[0]:
                result = canonical[1]
                cache[key] = (block, result)
                return result
            packed = []
            for p in points:
                if len(p) != 3 or not all(math.isfinite(float(c)) for c in p):
                    return None
                packed.append(_point_bytes(p))
            raw = b"".join(a + b for a, b in zip(packed, packed[1:]) if a != b)
            if raw:
                result = (hashlib.sha256(raw).hexdigest(), raw)
                entry[2][canonical_key] = (points, result)
        except (KeyError, TypeError, ValueError, OverflowError, struct.error):
            return None
        cache[key] = (block, result)
        return result
