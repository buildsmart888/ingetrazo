"""Opt-in Windows/OpenGL RC selection replay in its own source-host window.

Reuses the repository's native interaction driver. Qt events are synthetic;
this is source-host evidence, not packaged-host or physical-mouse acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def replay(model, output):
    from PySide6.QtCore import Qt
    from core import bim
    from scripts.bench_interaction import Driver, summarise
    from core.version import __version__ as host_version
    from PySide6 import __version__ as pyside_version

    input_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    driver = Driver(width=1440, height=960)
    original = bim.collect_objects
    collections = []

    def counted(scene):
        collections.append(1)
        return original(scene)

    bim.collect_objects = counted
    try:
        errors = driver.win._extension_load_errors
        if "go_rc_detailing" in errors:
            raise RuntimeError(errors["go_rc_detailing"])
        plugin = sys.modules.get("ingetrazo_plugin_go_rc_detailing")
        if plugin is None:
            raise RuntimeError("GO RC Detailing was not discovered by the host")
        display = importlib.import_module(plugin.__name__ + ".dual_display")
        opened, first_frame = driver.open(model)
        driver.win.bim_tray.show()
        driver.win._activate_tool("select")
        driver.settle(150)
        points = driver.model_points(6)
        rows = []
        for mode in ("solid", "wire", "both"):
            display.set_mode(driver.vp.scene, mode)
            driver.vp.notify_scene_changed()
            driver.vp.update()
            driver.settle(150)
            events, actual_selections = [], []
            collections.clear()
            for x, y in points:
                events.append(driver.step(lambda: driver.mouse(
                    "press", x, y, Qt.LeftButton, Qt.LeftButton)))
                events.append(driver.step(lambda: driver.mouse(
                    "release", x, y, Qt.LeftButton, Qt.NoButton)))
                actual_selections.append(len(driver.vp.scene.selection))
            totals = [round(sum(events[i][:4]) + sum(events[i + 1][:4]), 3)
                      for i in range(0, len(events), 2)]
            clicks = {
                "timing_per_press_or_release": summarise(events),
                "full_click_totals_ms": totals, "first_click_ms": totals[0],
                "repeated_click_median_ms": round(median(totals[1:]), 3),
                "selected_entities": actual_selections,
                "bim_collections": len(collections),
            }
            boxes = []
            for crossing in (False, True):
                width, height = driver.vp.width(), driver.vp.height()
                start, end = ((12, 12), (width - 12, height - 12))
                if crossing:
                    start, end = end, start
                collections.clear()
                samples = [driver.step(lambda: driver.mouse(
                    "press", *start, Qt.LeftButton, Qt.LeftButton))]
                for fraction in (0.25, 0.5, 0.75, 1.0):
                    x = start[0] + (end[0] - start[0]) * fraction
                    y = start[1] + (end[1] - start[1]) * fraction
                    samples.append(driver.step(lambda: driver.mouse(
                        "move", x, y, Qt.NoButton, Qt.LeftButton)))
                samples.append(driver.step(lambda: driver.mouse(
                    "release", *end, Qt.LeftButton, Qt.NoButton)))
                selected = list(driver.vp.scene.selection)
                boxes.append({
                    "crossing": crossing, "timing": summarise(samples),
                    "release_ms": round(sum(samples[-1][:4]), 3),
                    "event_totals_ms": [round(sum(event[:4]), 3) for event in samples],
                    "selected_entities": len(selected),
                    "selected_bars": sum((getattr(g, "ifc", None) or {}).get("class")
                                         == "IfcReinforcingBar" for g in selected),
                    "bim_collections": len(collections),
                })
            driver.win.grab().save(str(output / (mode + ".png")))
            rows.append({"mode": mode, "clicks": clicks, "boxes": boxes})
        report = {
            "scope": "source-host native Windows/OpenGL, synthetic Qt events, vsync disabled",
            "model": model.name, "renderer": driver.renderer,
            "host": host_version, "pyside6": pyside_version,
            "plugin_discovery": "PASS", "open_s": opened,
            "first_open_frame_ms": first_frame * 1000, "modes": rows,
            "acceptance": {
                "input_file_unchanged": hashlib.sha256(model.read_bytes()).hexdigest() == input_hash,
                "box_selection_hits_real_bars": all(
                    box["selected_bars"] == (0 if row["mode"] == "wire" else 181)
                    for row in rows for box in row["boxes"]),
                "selection_does_not_recollect_bim": all(
                    row["clicks"]["bim_collections"] == 0
                    and all(box["bim_collections"] == 0 for box in row["boxes"])
                    for row in rows),
            },
            "not_tested": ["packaged host", "physical mouse", "whole-building scale"],
        }
        (output / "native-selection.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        return report
    finally:
        bim.collect_objects = original
        driver.win._saved_content = driver.vp.scene.content_version
        driver.win._saved_version = driver.vp.scene.version
        driver.win.close()
        driver.app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    model, output = args.model.resolve(strict=True), args.output.resolve()
    sys.path.insert(0, str(ROOT))
    if args.child:
        output.mkdir(parents=True, exist_ok=False)
        from PySide6.QtCore import QSettings

        QSettings.setDefaultFormat(QSettings.IniFormat)
        for scope in (QSettings.UserScope, QSettings.SystemScope):
            QSettings.setPath(QSettings.IniFormat, scope, os.environ["APPDATA"])
        report = replay(model, output)
        print(json.dumps(report, indent=2))
        return 0 if all(report["acceptance"].values()) else 1

    # The graphics driver may hold its GL cache open until process exit.
    # Clean the temporary directory in the parent after the worker releases it.
    with tempfile.TemporaryDirectory(prefix="go-rc-native-") as temporary:
        env = os.environ.copy()
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            env[key] = temporary
        env["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "xcb"
        target = Path(temporary) / "ingetrazo" / "plugins" / "go_rc_detailing"
        shutil.copytree(ROOT / "extensions" / "go-rc-detailing" / "go_rc_detailing",
                        target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return subprocess.call(
            [sys.executable, str(Path(__file__).resolve()), str(model),
             "--output", str(output), "--child"], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
