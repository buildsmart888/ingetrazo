# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible CPU benchmark for repeated RB9 components and BIM selection.

Run from a checkout, for example::

    python benchmarks/rebar_interaction.py --counts 100 1000 10000 \
        --output /tmp/rebar-interaction.json

An optional --baseline-ref REV measures the old core.bim.collect_objects
against the patched collector on the SAME 19-component scene. Only the
read-only source of core/bim.py is loaded from that local Git revision;
the baseline never runs on the 10,000-object scene.

These are CPU collection, table-construction and selection-notification
measurements in an offscreen Qt process. They are NOT OpenGL frame rate,
picking latency, full click-to-visible-highlight latency or a workstation
performance guarantee. Table painting/event processing is outside timing.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PySide6  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent, qVersion  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import bim  # noqa: E402
from core import group as group_module  # noqa: E402
from core.scene import Scene  # noqa: E402
from views.tray import BimPanel  # noqa: E402


_SPEC = importlib.util.spec_from_file_location(
    "rb9_benchmark_geometry", ROOT / "scripts" / "GO_RB9_Stirrup_Fix.py")
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)


def _elapsed(call):
    started = time.perf_counter_ns()
    result = call()
    return (time.perf_counter_ns() - started) / 1e6, result


def _summary(samples):
    ordered = sorted(samples)
    return {"samples": len(samples), "median_ms": statistics.median(samples),
            "p95_ms": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
            "min_ms": ordered[0], "max_ms": ordered[-1]}


@contextmanager
def _count_geometry_calls(module):
    counts = {"collect_objects": 0, "face_set_area": 0,
              "face_set_volume": 0, "class_quantities": 0,
              "world_mesh": 0, "transformed_mesh": 0}

    def counted(name, original):
        def wrapper(*args, **kwargs):
            counts[name] += 1
            return original(*args, **kwargs)
        return wrapper

    with ExitStack() as stack:
        for name in ("collect_objects", "face_set_area", "face_set_volume",
                     "class_quantities"):
            stack.enter_context(patch.object(module, name, counted(name, getattr(module, name))))
        for name in ("world_mesh", "transformed_mesh"):
            stack.enter_context(patch.object(
                group_module, name, counted(name, getattr(group_module, name))))
        yield counts


def _scene(count):
    scene = Scene()
    definition = demo._rebar_definition(
        demo.stirrup_path(0.0), demo.STIRRUP_DIAMETER, (0.1, 0.3, 0.9, 1.0), "RB9")
    for i in range(count):
        scene.groups.append(demo._rebar_instance(
            definition, (i * demo.SPACING, 0.0, 0.0), f"Benchmark_RB9_{i + 1}",
            demo.STIRRUP_DIAMETER))
    return scene


def _collect_measurements(module, scene, repeats):
    times = []
    with _count_geometry_calls(module) as calls:
        for _ in range(repeats):
            elapsed, objects = _elapsed(lambda: module.collect_objects(scene))
            if len(objects) != len(scene.groups):
                raise RuntimeError("Quantity collection lost instances.")
            times.append(elapsed)
    return {**_summary(times), "total_function_calls": calls,
            "calls_per_collection": {name: value / repeats for name, value in calls.items()}}


def _panel_measurements(scene, samples):
    window = SimpleNamespace(viewport=SimpleNamespace(scene=scene))
    with _count_geometry_calls(bim) as cold_calls:
        elapsed, panel = _elapsed(lambda: BimPanel(window))
    try:
        rows = [panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())]
        times = []
        with _count_geometry_calls(bim) as selection_calls:
            for i in range(samples):
                group = scene.groups[(i * 997) % len(scene.groups)]

                def select_and_notify():
                    scene.select([group])
                    panel.refresh(force=False)

                measured, _ = _elapsed(select_and_notify)
                times.append(measured)
        rows_preserved = (len(rows) == len(scene.groups)
                          and all(panel.tree.topLevelItem(i) is row
                                  for i, row in enumerate(rows)))
        if not rows_preserved or any(selection_calls.values()):
            raise RuntimeError("Selection rebuilt BIM geometry or table rows.")
        return {
            "cold_panel_construction": {"elapsed_ms": elapsed,
                                        "function_calls": cold_calls},
            "selection_plus_bim_notification": {
                **_summary(times), "total_function_calls": selection_calls,
                "table_row_identity_preserved": rows_preserved,
            },
        }
    finally:
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _baseline(ref, repeats):
    sha = _git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
    source = _git("show", sha + ":core/bim.py")
    module = ModuleType("_rebar_benchmark_baseline_bim")
    exec(compile(source, f"{sha}:core/bim.py", "exec"), module.__dict__)
    scene = _scene(19)
    return {"baseline_commit": sha, "instances": 19,
            "comparison": "Same shared local mesh and transforms for both collectors",
            "baseline_collect_objects": _collect_measurements(module, scene, repeats),
            "patched_collect_objects": _collect_measurements(bim, scene, repeats)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--repeats", type=int, default=3,
                        help="Fresh quantity-cache collections per scene (default: 3)")
    parser.add_argument("--selection-samples", type=int, default=50)
    parser.add_argument("--baseline-ref", help="Optional local Git revision for 19-object comparison")
    parser.add_argument("--output", type=Path, help="Write the JSON result as well as stdout")
    args = parser.parse_args()
    if min([*args.counts, args.repeats, args.selection_samples]) < 1:
        parser.error("Counts, repeats and selection samples must be positive.")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    result = {
        "scope": "CPU quantities and offscreen BIM table; no picking, GPU or visible paint timing",
        "environment": {
            "python": sys.version, "platform": platform.platform(),
            "machine": platform.machine(), "logical_cpu_count": os.cpu_count(),
            "pyside6": PySide6.__version__, "qt": qVersion(),
            "qt_platform": app.platformName(), "git_head": _git("rev-parse", "HEAD"),
            "working_tree_has_changes": bool(_git("status", "--porcelain")),
        },
        "method": {
            "model": "Only identical RB9 stirrups, one shared prototype, distinct translations",
            "collect_objects": "Fresh QuantityCache on every call; no precomputed quantity results",
            "selection": "Scene.select then BimPanel.refresh(force=False); no event-loop painting",
            "timing": "perf_counter_ns; includes lightweight function-call counter wrappers",
        },
        "scenes": [],
    }
    for count in args.counts:
        build_ms, scene = _elapsed(lambda: _scene(count))
        meshes = {id(g.mesh): g.mesh for g in scene.groups}
        result["scenes"].append({
            "instances": count, "unique_meshes": len(meshes),
            "stored_mesh_faces": sum(len(m.faces) for m in meshes.values()),
            "placed_triangles": sum(len(g.mesh.faces) for g in scene.groups),
            "component_construction_ms": build_ms,
            "cold_quantity_collections": _collect_measurements(bim, scene, args.repeats),
            **_panel_measurements(scene, args.selection_samples),
        })
    if args.baseline_ref:
        result["baseline_19_comparison"] = _baseline(args.baseline_ref, args.repeats)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
