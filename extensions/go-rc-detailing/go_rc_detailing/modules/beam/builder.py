"""Orchestrates accepted beam stages as ordinary imported Python code."""
from __future__ import annotations
from types import SimpleNamespace
from time import perf_counter
from . import geometry, scene, export


def build_model(domain, progress=None, dual_display=False):
    state=SimpleNamespace(dual_display_enabled=bool(dual_display))
    phases=[
        ("prepare",geometry.prepare),
        ("geometry",geometry.create_parts),
        ("scene",scene.assemble),
        ("verification",scene.verify_and_publish),
        ("export",export.write_outputs),
        ("report",export.finish),
    ]
    timings={}
    percentages = (19, 32, 52, 70, 82, 90)
    for (name,fn), percentage in zip(phases, percentages):
        if progress is not None:
            progress.report(percentage, "Beam stage / " + name)
            if name == "export":
                # IFC/CSV is outside host Undo; prevent mid-output cancel.
                progress.commit()
        t0=perf_counter()
        fn(domain,state)
        timings[name]=round((perf_counter()-t0)*1000.0,2)
    print("GO RC Phase2 stage timings (ms):",timings)
    return state
