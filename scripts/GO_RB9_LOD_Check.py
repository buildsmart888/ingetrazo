# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only rebar display check for the IngeTrazo Python Console.

Run with Extensions > Python Console > Run script file. This file also works
in an older host without core.rebar_display. It never attaches, repairs or
infers a centreline, and does not start an interaction or change the model.
"""
import importlib
import math
import struct
import sys
from collections import Counter


_RENDERER_METHODS = (
    "_rebar_proxy", "_draw_rebar_centerlines", "_rebar_lod_active", "_instanced_eligible",
)


def _host_has_line_renderer(viewport):
    return viewport is not None and all(
        callable(getattr(type(viewport), name, None))
        and callable(getattr(viewport, name, None))
        for name in _RENDERER_METHODS
    )


def _load_diagnostics():
    try:
        module = importlib.import_module("core.rebar_display")
    except ImportError as error:
        return None, str(error)
    helper = getattr(module, "describe_centerline", None)
    if not callable(helper):
        return None, "The installed helper has no diagnostic API."
    return helper, None


def _stored_objects(scene):
    """Visit each stored group once, including nested groups, without cycles."""
    pending = list(getattr(scene, "groups", ()))
    seen = set()
    while pending:
        group = pending.pop()
        if id(group) in seen:
            continue
        seen.add(id(group))
        yield group
        pending.extend(getattr(group, "children", None) or ())


def _is_rebar(group):
    ext, tag = getattr(group, "ext", None), getattr(group, "ifc", None)
    layer = getattr(group, "layer", None)
    return ((isinstance(ext, dict) and "go_rebar" in ext)
            or (isinstance(tag, dict) and tag.get("class") == "IfcReinforcingBar")
            or getattr(layer, "name", layer) == "IfcReinforcingBar")


def _raw_description(group):
    """Inspect legacy data without claiming that it matches the solid mesh."""
    info = {"status": "missing", "reason": "missing_metadata", "points": 0,
            "diameter_m": None, "has_signature": False, "render_supported": None}
    ext = getattr(group, "ext", None)
    if not isinstance(ext, dict) or "go_rebar" not in ext:
        return info
    block = ext["go_rebar"]
    info.update(status="invalid", reason="invalid_metadata")
    if not isinstance(block, dict):
        return info
    points = block.get("centerline")
    if isinstance(points, (list, tuple)):
        info["points"] = len(points)
    signature = block.get("mesh_signature")
    info["has_signature"] = isinstance(signature, str) and bool(signature)
    try:
        diameter = float(block["diameter_m"])
        if math.isfinite(diameter) and diameter > 0:
            info["diameter_m"] = diameter
        valid = (block.get("version") == 1 and info["points"] >= 2
                 and info["diameter_m"] is not None
                 and isinstance(block.get("definition_key"), str)
                 and all(len(p) == 3 and all(math.isfinite(float(c)) for c in p)
                         for p in points))
        if valid:
            packed = [struct.pack("<3f", *point) for point in points]
            valid = any(a != b for a, b in zip(packed, packed[1:]))
    except (KeyError, TypeError, ValueError, OverflowError, struct.error):
        valid = False
    if valid and signature is None:
        info.update(status="unsigned", reason="missing_signature")
    elif valid and info["has_signature"]:
        info.update(status="unverified", reason="validator_unavailable")
    return info


def collect_report(scene, viewport=None):
    """Return host/data diagnostics without changing geometry or selection."""
    helper, helper_error = _load_diagnostics()
    supported = _host_has_line_renderer(viewport)
    module = sys.modules.get(type(viewport).__module__) if viewport is not None else None
    stored = list(_stored_objects(scene))
    nested_ids = {id(child) for group in stored
                  for child in (getattr(group, "children", None) or ())}
    bars = [group for group in stored if _is_rebar(group)]
    details = []
    path_meshes = set()
    for group in bars:
        info = helper(group, viewport) if helper is not None else _raw_description(group)
        info = dict(info, name=str(getattr(group, "name", "Unnamed")),
                    placement_context_assessed=id(group) not in nested_ids)
        if not info["placement_context_assessed"]:
            info["render_supported"] = None
        details.append(info)
        if info["points"] >= 2:
            mesh = getattr(group, "mesh", None)
            if mesh is not None:
                path_meshes.add(id(mesh))
    blockers = []
    if getattr(scene, "edit_group", None) is not None:
        blockers.append("group_edit")
    section = getattr(scene, "active_section", None)
    if (getattr(scene, "show_section_cuts", True) and callable(section)
            and section() is not None):
        blockers.append("section_cut")
    nested_unchecked = sum(not info["placement_context_assessed"] for info in details)
    return {
        "host_line_renderer": supported,
        "running_application": sys.executable,
        "viewport_module": getattr(module, "__file__", "Not available"),
        "frozen_application": bool(getattr(sys, "frozen", False)),
        "diagnostic_helper": helper is not None,
        "diagnostic_helper_error": helper_error,
        "bar_objects": len(bars),
        "centerline_data": sum(info["points"] >= 2 for info in details),
        "signed_paths": sum(info["has_signature"] for info in details),
        "path_mesh_definitions": len(path_meshes),
        "eligible_for_lines": (sum(info["render_supported"] is True for info in details)
                               if supported and helper is not None and not nested_unchecked
                               else None),
        "nested_bars_unchecked": nested_unchecked,
        "blockers": blockers,
        "interaction_suspended": bool(getattr(viewport, "_rebar_lod_suspended", False)),
        "bars": details,
    }


def print_report(report):
    """Print a compact result suitable for sharing with a bug report."""
    total = report["bar_objects"]
    renderer = "AVAILABLE" if report["host_line_renderer"] else "MISSING"
    eligible = report["eligible_for_lines"]
    print("GO RB9 DISPLAY CHECK (read-only)")
    print("HOST_LINE_RENDERER: " + renderer)
    print("CENTERLINE_DATA: {}/{} bars with at least 2 stored points".format(
        report["centerline_data"], total))
    print("SIGNED_PATHS: {}/{}".format(report["signed_paths"], total))
    print("ELIGIBLE_FOR_LINES: " + ("NOT CHECKED" if eligible is None
                                   else "{}/{}".format(eligible, total)))
    print("PATH_MESH_DEFINITIONS: {}".format(report["path_mesh_definitions"]))
    print("NESTED_BARS_UNCHECKED: {}".format(report["nested_bars_unchecked"]))
    print("INTERACTION_BLOCKERS: " + (", ".join(report["blockers"]) or "none"))
    print("RUNNING_APPLICATION: " + report["running_application"])
    print("VIEWPORT_MODULE: " + str(report["viewport_module"]))
    print("FROZEN_APPLICATION: {}".format(report["frozen_application"]))
    if not report["diagnostic_helper"]:
        print("DATA_VALIDATOR: UNAVAILABLE; stored points/signatures are not verified")
        print("  " + report["diagnostic_helper_error"])

    counts = Counter((info["points"], info["diameter_m"], info["status"], info["reason"])
                     for info in report["bars"])
    for (points, diameter, status, reason), count in counts.most_common(12):
        size = "unknown diameter" if diameter is None else "{:g} mm".format(diameter * 1000)
        label = "DATA VERIFIED" if status == "ready" else status.upper()
        print("  {} bars: {} points, {}, {} ({})".format(
            count, points, size, label, reason))
    if len(counts) > 12:
        print("  {} additional data categories in GO_RB9_LOD_REPORT['bars'].".format(
            len(counts) - 12))

    if not report["host_line_renderer"]:
        print("ACTION: Start IngeTrazo from branch fix/rebar-lod-v0.5.9.")
        print("A downloaded modelling script cannot install the viewport renderer.")
    if not total:
        print("ACTION: No rebar metadata or IfcReinforcingBar tags were found in this document.")
    elif any(info["status"] in ("missing", "unsigned", "stale", "invalid")
             for info in report["bars"]):
        print("ACTION: Rebuild the affected bars with their updated producer in the updated host.")
        print("For this demo, use GO_RB9_Stirrup_Fix.py in a new document first.")
    if report["blockers"]:
        print("ACTION: Finish group editing or disable the indicated display blocker.")
    if report["nested_bars_unchecked"]:
        print("NOTE: Nested bars need their inherited placement/material context checked.")
        print("Their stored data alone does not establish eligibility for every placement.")
    if report["interaction_suspended"]:
        print("NOTE: Interaction is paused after focus loss, normally while this console is open.")
        print("Return to the viewport; the next navigation or move gesture resumes it.")
    if eligible == total and total and not report["blockers"]:
        print("READY: Focus the viewport, then orbit, pan, zoom or preview moving a bar.")
        print("The idle view is intentionally solid; this check does not activate line mode.")
    elif report["host_line_renderer"] and not report["diagnostic_helper"]:
        print("ACTION: Restart with the updated host to validate the stored paths.")
    print("No geometry, centreline data or display mode was changed by this script.")


if "scene" in globals():
    GO_RB9_LOD_REPORT = collect_report(scene, globals().get("viewport"))
    print_report(GO_RB9_LOD_REPORT)
elif __name__ == "__main__":
    print("Open IngeTrazo > Extensions > Python Console > Run script file...")
