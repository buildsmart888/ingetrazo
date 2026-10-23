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
import time


ROOT = Path(__file__).resolve().parents[1]


def replay(model, output, modes=("solid", "wire", "both"), navigation=False, storey=None):
    from PySide6.QtCore import Qt
    from core import bim
    from scripts.bench_interaction import Driver, summarise
    from core.version import __version__ as host_version
    from PySide6 import __version__ as pyside_version

    def progress(stage):
        (output / "progress.json").write_text(
            json.dumps({"stage": stage}) + "\n", encoding="utf-8", newline="\n")

    progress("source_host_startup")
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
        progress("model_open_and_first_frame")
        opened, first_frame = driver.open(model)
        if storey is not None:
            for group in driver.vp.scene.groups:
                record = (group.ext or {}).get("go_rc_scale")
                if record:
                    group.hidden = record["storey"] != storey
            driver.vp.scene.version += 1
            driver.vp.notify_scene_changed()
            driver.home()
        driver.win.bim_tray.show()
        driver.win._activate_tool("select")
        driver.settle(150)
        points = driver.model_points(6)
        expected_bars = sum((g.ifc or {}).get("class") == "IfcReinforcingBar"
                            and driver.vp.scene.entity_visible(g) for g in driver.vp.scene.groups)
        rows = []
        for mode in modes:
            progress(mode + ":display_mode")
            # Avoid a needless document-wide wire rebuild for Solid, which
            # is already the saved mode of the stress fixtures.
            if display.get_mode(driver.vp.scene) != mode:
                display.set_mode(driver.vp.scene, mode)
            driver.vp.notify_scene_changed()
            driver.vp.update()
            driver.settle(150)
            selectable_bars = sum((g.ifc or {}).get("class") == "IfcReinforcingBar"
                                  and driver.vp.scene.entity_selectable(g)
                                  for g in driver.vp.scene.groups)
            events, actual_selections = [], []
            collections.clear()
            for x, y in points:
                progress(mode + ":click_selection")
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
            (output / "partial-results.json").write_text(json.dumps({
                "mode": mode, "clicks": clicks, "boxes": [],
                "expected_selectable_bars": selectable_bars,
            }, indent=2) + "\n", encoding="utf-8", newline="\n")
            boxes = []
            for crossing in (False, True):
                progress(mode + (":crossing_selection" if crossing else ":window_selection"))
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
                (output / "partial-results.json").write_text(json.dumps({
                    "mode": mode, "clicks": clicks, "boxes": boxes,
                    "expected_selectable_bars": selectable_bars,
                }, indent=2) + "\n", encoding="utf-8", newline="\n")
            navigation_results = {}
            if navigation:
                progress(mode + ":orbit")
                driver.vp.scene.clear_selection()
                driver.vp.notify_scene_changed()
                driver.home()
                x, y = driver.vp.width() / 2, driver.vp.height() / 2
                samples = [driver.step(lambda: driver.mouse(
                    "press", x, y, Qt.MiddleButton, Qt.MiddleButton))]
                for index in range(12):
                    samples.append(driver.step(lambda index=index: driver.mouse(
                        "move", x + 4 * (index + 1), y + 2 * (index + 1),
                        Qt.NoButton, Qt.MiddleButton)))
                samples.append(driver.step(lambda: driver.mouse(
                    "release", x + 48, y + 24, Qt.MiddleButton, Qt.NoButton)))
                navigation_results["orbit"] = summarise(samples)
                progress(mode + ":zoom")
                samples = [driver.step(lambda n=n: driver.wheel(x, y, 1 if n < 4 else -1))
                           for n in range(8)]
                driver.settle(250)
                navigation_results["zoom"] = summarise(samples)
            driver.win.grab().save(str(output / (mode + ".png")))
            rows.append({"mode": mode, "clicks": clicks, "boxes": boxes,
                         "navigation_unselected": navigation_results,
                         "expected_selectable_bars": selectable_bars})
        report = {
            "scope": "source-host native Windows/OpenGL, synthetic Qt events, vsync disabled",
            "model": model.name, "renderer": driver.renderer,
            "host": host_version, "pyside6": pyside_version,
            "plugin_discovery": "PASS", "open_s": opened,
            "first_open_frame_ms": first_frame * 1000, "modes": rows,
            "visible_bars": expected_bars, "active_storey": storey,
            "acceptance": {
                "input_file_unchanged": hashlib.sha256(model.read_bytes()).hexdigest() == input_hash,
                "box_selection_hits_real_bars": all(
                    box["selected_bars"] == row["expected_selectable_bars"]
                    for row in rows for box in row["boxes"]),
                "selection_does_not_recollect_bim": all(
                    row["clicks"]["bim_collections"] == 0
                    and all(box["bim_collections"] == 0 for box in row["boxes"])
                    for row in rows),
            },
            "not_tested": ["packaged host", "physical mouse", "engineered building design"],
        }
        progress("completed")
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
    parser.add_argument("--modes", nargs="+", choices=("solid", "wire", "both"),
                        default=["solid", "wire", "both"])
    parser.add_argument("--navigation", action="store_true")
    parser.add_argument("--storey", type=int)
    parser.add_argument("--max-private-mb", type=int, default=0)
    parser.add_argument("--min-free-mb", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    model, output = args.model.resolve(strict=True), args.output.resolve()
    sys.path.insert(0, str(ROOT))
    if args.child:
        output.mkdir(parents=True, exist_ok=False)
        from PySide6.QtCore import QSettings

        QSettings.setDefaultFormat(QSettings.IniFormat)
        for scope in (QSettings.UserScope, QSettings.SystemScope):
            QSettings.setPath(QSettings.IniFormat, scope, os.environ["APPDATA"])
        report = replay(model, output, args.modes, args.navigation, args.storey)
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
        command = [sys.executable, str(Path(__file__).resolve()), str(model),
                   "--output", str(output), "--child", "--modes", *args.modes]
        if args.navigation:
            command.append("--navigation")
        if args.storey is not None:
            command.extend(["--storey", str(args.storey)])
        return guarded_run(command, env, output, args)


def guarded_run(command, env, output, args):
    """Bound this worker tree; never terminate an existing user application."""
    import psutil  # Optional QA dependency, not a host runtime dependency.

    if output.exists():
        raise FileExistsError(output)
    initial_available = psutil.virtual_memory().available / 1048576
    if args.min_free_mb and initial_available < args.min_free_mb + 128:
        output.mkdir(parents=True)
        (output / "resource-guard.json").write_text(json.dumps({
            "status": "INSUFFICIENT_STARTUP_HEADROOM",
            "initial_machine_available_mb": round(initial_available, 2),
            "required_startup_available_mb": args.min_free_mb + 128,
            "worker_started": False,
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        return 1
    start = time.monotonic()
    peak_private = peak_rss = 0
    minimum_available = float("inf")
    reason = None
    process = subprocess.Popen(command, cwd=ROOT, env=env)
    owner = psutil.Process(process.pid)
    while process.poll() is None:
        try:
            workers = [owner, *owner.children(recursive=True)]
            memory = [worker.memory_info() for worker in workers if worker.is_running()]
            private = sum(getattr(info, "private", info.rss) for info in memory) / 1048576
            rss = sum(info.rss for info in memory) / 1048576
            available = psutil.virtual_memory().available / 1048576
            peak_private, peak_rss = max(peak_private, private), max(peak_rss, rss)
            minimum_available = min(minimum_available, available)
            if args.max_private_mb and private > args.max_private_mb:
                reason = "PRIVATE_MEMORY_LIMIT"
            elif args.min_free_mb and available < args.min_free_mb:
                reason = "AVAILABLE_MEMORY_LIMIT"
            elif time.monotonic() - start > args.timeout:
                reason = "TIMEOUT"
            if reason:
                for worker in reversed(workers):
                    if worker.is_running():
                        worker.terminate()
                psutil.wait_procs(workers, timeout=10)
                break
        except psutil.NoSuchProcess:
            pass
        time.sleep(0.1)
    code = process.wait()
    # A venv launcher can finish before its Python/driver worker has released
    # inherited handles. Wait for the last observed descendants too.
    if "workers" in locals():
        psutil.wait_procs(workers, timeout=10)
    output.mkdir(parents=True, exist_ok=True)
    guard = {
        "status": reason or ("PASS" if code == 0 else "EXIT_NONZERO"),
        "worker_exit_code": code, "elapsed_s": round(time.monotonic() - start, 3),
        "peak_worker_tree_private_mb": round(peak_private, 2),
        "peak_worker_tree_rss_mb": round(peak_rss, 2),
        "minimum_machine_available_mb": (round(minimum_available, 2)
                                         if minimum_available != float("inf") else None),
        "private_limit_mb": args.max_private_mb, "available_floor_mb": args.min_free_mb,
        "timeout_s": args.timeout,
    }
    (output / "resource-guard.json").write_text(
        json.dumps(guard, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(guard), flush=True)
    return 0 if reason is None and code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
