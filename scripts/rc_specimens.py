"""Reproduce GO RC v0.10.3 specimens in a disposable source-host document.

No engineering redesign, installed-host mutation or OpenGL/FPS claim is made.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "extensions" / "go-rc-detailing" / "go_rc_detailing"


def load_plugin():
    from core.extensions import _import_by_path

    name = "ingetrazo_plugin_go_rc_detailing"
    module = sys.modules.get(name)
    if module is None:
        module = _import_by_path("go_rc_detailing", PACKAGE / "__init__.py")
    elif Path(module.__file__).resolve() != (PACKAGE / "__init__.py").resolve():
        raise RuntimeError("A different GO RC package is already loaded")
    return module


def plugin_module(relative):
    return importlib.import_module(load_plugin().__name__ + "." + relative)


def build_specimens(output):
    """Build through real plugin phases; exports stay under explicit output."""
    from core import bim
    from core.group import Group
    from core.mesh import Mesh
    from core.scene import Scene
    from PySide6.QtGui import QMatrix4x4

    scene = Scene()
    sentinel = Group(Mesh(), name="Existing user object - must survive")
    scene.groups.append(sentinel)
    scope = dict(scene=scene, Mesh=Mesh, Group=Group, bim=bim)
    adapter = plugin_module("beam_adapter")
    plugin_module("adapters.ingetrazo.compat").require_supported_host(2)
    adapter.assert_baseline_locked()
    geometry = plugin_module("modules.beam.geometry")
    assembly = plugin_module("modules.beam.scene")
    native = plugin_module("native_bim_mode")
    specimens = []
    for identifier, spans, y in (
        ("QA_SB", [4.0], 0.0),
        ("QA_CB", [4.0, 3.5, 4.5], 3.0),
    ):
        start = perf_counter()
        domain = adapter._static_domain(scope)
        domain.BEAM_ID, domain.SPANS_M = identifier, spans
        domain.B, domain.H = 0.30, 0.50
        domain.SHOW_MARK_LABELS = domain.VERIFY_SHOW_REPORT = False
        state = SimpleNamespace(dual_display_enabled=True)
        geometry.prepare(domain, state)
        geometry.create_parts(domain, state)
        assembly.assemble(domain, state)
        # Distinct specimen placements exercise parent-to-leaf transforms.
        state.parent.xform = QMatrix4x4()
        state.parent.xform.translate(0.0, y, 0.0)
        assembly.verify_and_publish(domain, state)
        native.expose_native_bim(scene, state.parent, prefix=identifier)
        specimens.append({
            "id": identifier, "kind": "beam", "spans_m": spans,
            "section_mm": [300, 500], "bars": len(state.bar_meta),
            "ties": len(state.stirrup_stations),
            "length_m": sum(row["length_m"] for row in state.bar_meta.values()),
            "mass_kg": sum(row["weight_kg"] for row in state.bar_meta.values()),
            "verification_issues": len(state.verification["issues"]),
            "build_ms": round((perf_counter() - start) * 1000, 3),
        })
    columns = plugin_module("modules.column.builder")
    params = plugin_module("modules.column.params")
    for identifier, shape, x in (("QA_CR", "rect", 0.0), ("QA_CC", "circular", 3.0)):
        start = perf_counter()
        p = params.ColumnParams(
            column_id=identifier, shape=shape, pos_x_mm=x * 1000,
            pos_y_mm=6000, export_ifc=False,
        )
        meta = columns.create_column(p, scope, out_base=output, dual_display=True)
        specimens.append({
            "id": identifier, "kind": "column", "shape": shape,
            "height_mm": p.height_mm, "bars": meta["main_bar_count"] + meta["tie_count"],
            "ties": meta["tie_count"], "spiral_turns": meta["spiral_turns"],
            "mass_kg": meta["steel_total_kg"],
            "build_ms": round((perf_counter() - start) * 1000, 3),
        })
    display = plugin_module("dual_display")
    display.refresh_wire_overlays(scene)
    # Notify source-host consumers once after building this disposable fixture.
    scene.version += 1
    assert scene.groups[0] is sentinel
    return scene, specimens


def solid_snapshot(scene):
    """Native IDs, accepted BBS data, placement and mesh sharing fingerprint."""
    from core.group import iter_placements

    rows, prototypes = [], {}
    for root in scene.groups:
        for group, transform in iter_placements(root):
            tag = group.ifc or {}
            if tag.get("class") != "IfcReinforcingBar":
                continue
            ext = group.ext or {}
            data = ext.get("go_rc_beam") or ext.get("go_rc_column") or {}
            reference = ext.get("go_rc_dual_display") or {}
            prototype = prototypes.setdefault(id(group.mesh), len(prototypes))
            rows.append({
                "uid": group.uid, "name": group.name, "ifc": tag,
                "metadata": data, "display_reference": reference,
                "matrix": list(transform.data()) if transform is not None else None,
                "prototype": prototype, "faces": len(group.mesh.faces),
                "edges": len(group.mesh.edges),
            })
    return {"bars": rows, "unique_bar_meshes": len(prototypes)}


def measure_bim_selection(scene):
    """CPU scene->BIM notification timings, without viewport painting/picking."""
    from core import bim
    from core.history import History
    from views.tray import BimPanel, BimTray

    window = SimpleNamespace(viewport=SimpleNamespace(
        scene=scene, history=History(scene), update=lambda: None))
    original = bim.collect_objects
    counts = {"collections": 0}

    def counted(document):
        counts["collections"] += 1
        return original(document)

    bim.collect_objects = counted
    panel = None
    try:
        start = perf_counter()
        panel = BimPanel(window)
        initial_ms = (perf_counter() - start) * 1000
        dock = SimpleNamespace(bim=panel)
        bars = [g for g in scene.groups if (g.ifc or {}).get("class") == "IfcReinforcingBar"]
        row_ids = [id(panel.tree.topLevelItem(i)) for i in range(panel.tree.topLevelItemCount())]
        times = []
        for chosen in ([bars[0]], [], bars[:20], bars, [], [bars[-1]], []):
            start = perf_counter()
            scene.select(chosen)
            BimTray.on_scene_changed(dock)
            times.append(round((perf_counter() - start) * 1000, 3))
        stable_rows = row_ids == [
            id(panel.tree.topLevelItem(i)) for i in range(panel.tree.topLevelItemCount())]
        return {
            "scope": "offscreen CPU scene selection plus native BIM notification; no picking/paint/GPU",
            "initial_collection_ms": round(initial_ms, 3),
            "selection_notifications_ms": times,
            "collection_calls_including_initial": counts["collections"],
            "rows_reused": stable_rows, "bim_rows": panel.tree.topLevelItemCount(),
        }
    finally:
        bim.collect_objects = original
        scene.clear_selection()
        if panel is not None:
            panel.deleteLater()


def run(output):
    from formats.igz import load_into, save_scene
    from core.scene import Scene
    from PySide6 import __version__ as qt_binding

    output.mkdir(parents=True, exist_ok=False)
    with (output / "build.log").open("w", encoding="utf-8") as log, redirect_stdout(log):
        scene, specimens = build_specimens(output / "column-outputs")
        before = solid_snapshot(scene)
        display = plugin_module("dual_display")
        mode_checks = {}
        for mode in display.MODES:
            stats = display.set_mode(scene, mode)
            mode_checks[mode] = {
                "solid_data_unchanged": solid_snapshot(scene) == before,
                "actual_mode": display.get_mode(scene), "wire": stats["wire"],
            }
        display.set_mode(scene, "solid")
        wire_stats = display.refresh_wire_overlays(scene)
        save_scene(scene, output / "four-rc-specimens.igz")
        loaded = Scene()
        load_into(loaded, output / "four-rc-specimens.igz")
        restored = solid_snapshot(loaded)
        selection = measure_bim_selection(loaded)
        complexity = asdict(plugin_module("performance").complexity_report(loaded))
    report = {
        "plugin": "GO RC Detailing 0.10.3 deployed snapshot",
        "host": "IngeTrazo 0.5.9 source", "python": sys.version.split()[0],
        "pyside6": qt_binding, "specimens": specimens, "complexity": complexity,
        "wire": wire_stats, "display_modes": mode_checks,
        "bar_count": len(before["bars"]), "bar_prototypes": before["unique_bar_meshes"],
        "persistence": {
            "native_ids_bbs_transforms_and_sharing_preserved": restored == before,
            # JSON persistence changes coordinate tuples into lists.
            "path_definitions_preserved": json.dumps(loaded.plugin_data, sort_keys=True)
            == json.dumps(scene.plugin_data, sort_keys=True),
            "existing_user_object_preserved": any(
                g.name == "Existing user object - must survive" for g in loaded.groups),
        },
        "bim_selection": selection,
        "not_tested": ["installed host", "mouse picking/box drag", "OpenGL frame time",
                       "whole-building scale", "engineering code compliance"],
    }
    report["acceptance"] = {
        "specimen_counts": [row["bars"] for row in specimens] == [40, 107, 25, 9],
        "beam_geometry_verification": all(
            row["verification_issues"] == 0 for row in specimens if row["kind"] == "beam"),
        "all_display_modes_preserve_solids": all(
            row["solid_data_unchanged"] and row["actual_mode"] == mode
            for mode, row in mode_checks.items()),
        "persistence": all(report["persistence"].values()),
        "selection_reuses_bim_quantities": (
            selection["collection_calls_including_initial"] == 1 and selection["rows_reused"]),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    # A separate process with disposable settings/data; never load user plugins.
    with tempfile.TemporaryDirectory(prefix="go-rc-specimens-") as temporary:
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            os.environ[key] = temporary
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        if sys.platform == "win32":
            os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["WINDIR"]) / "Fonts"))
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication

        QSettings.setDefaultFormat(QSettings.IniFormat)
        for scope in (QSettings.UserScope, QSettings.SystemScope):
            QSettings.setPath(QSettings.IniFormat, scope, temporary)
        application = QApplication.instance() or QApplication([])
        report = run(args.output.resolve())
        print(json.dumps(report, indent=2))
        application.processEvents()
    return 0 if all(report["acceptance"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
