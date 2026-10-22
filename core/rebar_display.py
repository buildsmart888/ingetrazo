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
        return self._get_proxy(group.mesh, block, revision)

    def _get_proxy(self, mesh, block, revision=None):
        """Validate local metadata independently of placement eligibility."""
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

    def _unsigned_path_valid(self, mesh, block, revision=None):
        """Check an unsigned path's format, without certifying its geometry."""
        serial = (revision, getattr(mesh, "_mut_serial", None), len(mesh.vertices),
                  len(mesh.edges), len(mesh.faces))
        entry = self._meshes.get(mesh)
        if entry is None or entry[0] != serial:
            entry = (serial, {}, {})
            self._meshes[mesh] = entry
        points = block["centerline"]
        key = (id(block), id(points), None)
        hit = entry[1].get(key)
        if hit is not None and hit[0] is block:
            return hit[1]
        # The None signature separates these format checks from verified
        # proxies. Native reload may duplicate otherwise identical blocks.
        canonical_key = (None, block["definition_key"], float(block["diameter_m"]))
        canonical = entry[2].get(canonical_key)
        if canonical is not None and points == canonical[0]:
            entry[1][key] = (block, True)
            return True
        valid = False
        try:
            previous = None
            for point in points:
                if len(point) != 3 or not all(math.isfinite(float(c)) for c in point):
                    valid = False
                    break
                packed = _point_bytes(point)
                if previous is not None and packed != previous:
                    valid = True
                previous = packed
        except (TypeError, ValueError, OverflowError, struct.error):
            valid = False
        if valid:
            entry[2][canonical_key] = (points, True)
        entry[1][key] = (block, valid)
        return valid


_DIAGNOSTIC_CENTERLINES = CenterlineCache()
_RENDERER_METHODS = (
    "_rebar_proxy", "_draw_rebar_centerlines", "_rebar_lod_active", "_instanced_eligible",
)


def host_renderer_available(viewport) -> bool:
    """Check the loaded viewport, not merely whether this helper is installed.

    A console script can import an updated helper while an older viewport
    class is still running. Instance-only attributes do not establish that
    the host's draw passes implement the representation switch.
    """
    return viewport is not None and all(
        callable(getattr(type(viewport), name, None))
        and callable(getattr(viewport, name, None))
        for name in _RENDERER_METHODS
    )


def describe_centerline(group, viewport=None) -> dict:
    """Describe stored rebar data and host support without changing the model.

    ``status`` is missing, unsigned, stale, invalid, ready or unsupported;
    ``reason`` is a stable code for a translated UI or console diagnosis.
    ``points`` counts stored points and ``diameter_m`` is positive and finite
    or None. ``has_signature`` reports a nonempty string signature.

    Host availability is separate: valid data may be ready while an older
    loaded viewport reports ``host_renderer_available=False``. That field
    is None when no viewport is supplied. ``render_supported`` is None
    without a capable host, otherwise a bool. It describes eligibility,
    never whether lines are currently active during an interaction.

    This may warm the existing CPU signature, proxy and material caches;
    it does not change metadata, geometry, selection, display mode or GPU
    resources. Metadata follows the renderer's immutable-block contract:
    replace the block on rebuild, or bump the scene content revision.
    """
    available = None if viewport is None else host_renderer_available(viewport)
    result = {
        "status": "missing", "reason": "missing_metadata", "points": 0,
        "diameter_m": None, "has_signature": False,
        "host_renderer_available": available,
        "render_supported": False if available else None,
    }

    def finish(status, reason):
        result["status"], result["reason"] = status, reason
        if available:
            result["render_supported"] = status == "ready"
        return result

    ext = getattr(group, "ext", None)
    if not isinstance(ext, dict) or "go_rebar" not in ext:
        return result
    block = ext["go_rebar"]
    if not isinstance(block, dict):
        return finish("invalid", "invalid_metadata")
    points = block.get("centerline")
    if isinstance(points, (list, tuple)):
        result["points"] = len(points)
    signature = block.get("mesh_signature")
    result["has_signature"] = isinstance(signature, str) and bool(signature)
    try:
        diameter = float(block["diameter_m"])
        if math.isfinite(diameter) and diameter > 0:
            result["diameter_m"] = diameter
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    if block.get("version") != 1:
        return finish("invalid", "unsupported_version")
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        return finish("invalid", "invalid_centerline")
    if result["diameter_m"] is None:
        return finish("invalid", "invalid_diameter")
    if not isinstance(block.get("definition_key"), str):
        return finish("invalid", "invalid_definition_key")
    if signature is not None and not result["has_signature"]:
        return finish("invalid", "invalid_signature")
    mesh = getattr(group, "mesh", None)
    if mesh is None:
        return finish("invalid", "missing_mesh")

    cache = getattr(viewport, "_rebar_centerlines", None)
    if not isinstance(cache, CenterlineCache):
        cache = _DIAGNOSTIC_CENTERLINES
    scene = getattr(viewport, "scene", None)
    revision = getattr(scene, "content_version", getattr(scene, "version", None))
    if signature is None:
        if not cache._unsigned_path_valid(mesh, block, revision):
            return finish("invalid", "invalid_centerline")
        return finish("unsigned", "missing_signature")
    if cache._get_proxy(mesh, block, revision) is None:
        if signature != mesh_signature(mesh):
            return finish("stale", "mesh_changed")
        return finish("invalid", "invalid_centerline")

    # These checks are per placement: siblings can share a valid definition
    # while one is a classic group, billboard or differently painted instance.
    if getattr(group, "xform", None) is None:
        return finish("unsupported", "classic_group")
    if getattr(group, "billboard", False):
        return finish("unsupported", "billboard")
    if getattr(group, "children", None):
        return finish("unsupported", "nested_children")
    if available:
        eligible = getattr(type(viewport), "_instanced_eligible")
        # Read the loaded renderer's switch, not a subsequently changed env
        # variable or a second module imported from another installation.
        if getattr(eligible, "__globals__", {}).get("_NO_INSTANCING", False):
            return finish("unsupported", "instancing_disabled")
        if not viewport._instanced_eligible(group):
            return finish("unsupported", "unsupported_material")
    return finish("ready", "verified")
