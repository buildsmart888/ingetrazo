"""Accepted beam v0.7 and opt-in static Phase2 beam pipeline.

The production fallback is kept until a real IngeTrazo GUI acceptance.
"""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path

BASELINE = Path(__file__).with_name("beam_baseline_v0_7.py")
BASELINE_SHA256 = "0c5da115addb87369755825ded91ea5187f5e14c645e0f02859bae60a0ca3baf"


def assert_baseline_locked():
    actual = hashlib.sha256(BASELINE.read_bytes()).hexdigest()
    if actual != BASELINE_SHA256:
        raise RuntimeError(
            "GO RC Beam v0.7 ACCEPTED BASELINE SHA-256 CHANGED. "
            "Beam generation is blocked until the baseline is restored. "
            f"expected={BASELINE_SHA256} actual={actual}")
    return actual


def baseline_namespace(scope):
    """LEGACY fallback and test-only: AST execution (retire after GUI acceptance).

    Load frozen baseline functions and constants without its final auto-run.

    AST removes ONLY the last top-level `if ...: build_model()` call. All
    function bodies, including accepted 90/135 tie geometry, are unchanged.
    """
    assert_baseline_locked()
    source = BASELINE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BASELINE))
    end = tree.body[-1]
    if not isinstance(end, ast.If) or "build_model" not in ast.unparse(end):
        raise RuntimeError("Unexpected baseline entrypoint: refusing to run")
    tree.body.pop()
    ast.fix_missing_locations(tree)
    namespace = dict(scope)
    namespace.setdefault("__name__", "__go_rc_baseline__")
    exec(compile(tree, str(BASELINE), "exec"), namespace)
    # Cross-section repair only; preserve frozen beam hook centreline.
    from .geometry_adapter import install_profile_adapter
    install_profile_adapter(namespace)
    return namespace


def _static_domain(scope):
    """Load ordinary Python modules and bind the current IngeTrazo host.

    Fresh parameters per build: no stale dialog globals from a previous beam.
    This is a normal Python import/reload, NEVER AST/exec of the legacy source.
    """
    import importlib
    from .modules.beam import domain
    domain = importlib.reload(domain)
    for name in ("scene", "Mesh", "Group", "bim"):
        if name not in scope:
            raise RuntimeError("IngeTrazo scope missing " + name)
        setattr(domain, name, scope[name])
    domain.window = scope.get("window")
    from .geometry_adapter import install_profile_adapter
    install_profile_adapter(domain.__dict__)
    return domain


def _mesh_preview_facets(domain, sides=8):
    """Optional NEW-BUILD render tessellation: preserve *all* bent axes.

    This only changes a circle from 12 to 8 facets. Bend/fillet segments,
    centreline length, stations and BBS remain bit-for-bit the same; native
    IFC geometry volume is an octagonal approximation, clearly documented.
    """
    if sides not in (8, 12):
        raise ValueError("Mesh preview facets must be 8 or 12")
    if sides == 12:
        return
    original = domain.make_rebar_mesh

    def lightweight_tube(*args, **kwargs):
        if len(args) > 5:
            raise ValueError("Explicit sides argument conflicts with preview quality")
        kwargs["sides"] = sides
        return original(*args, **kwargs)

    domain.make_rebar_mesh = lightweight_tube


def execute_beam(scope, mode="single", native_bim_visible=True,
                 pipeline="phase2", fast_mesh=False, progress=None,
                 dual_display=False):
    """Build one accepted beam inside IngeTrazo's undoable transaction.

    accepted -> locked AST fallback, unchanged from v0.8.2 (safe default)
    phase2   -> statically split, normal Python import path (opt-in).
    """
    if mode not in ("single", "multi"):
        raise ValueError("Unknown beam button")
    if pipeline not in ("accepted", "phase2"):
        raise ValueError("Unknown Beam Pipeline")
    if pipeline == "accepted":
        if fast_mesh:
            raise ValueError("8-facet preview is available only in Phase2 preview")
        ns = baseline_namespace(scope)
        get_param = ns["parameter_dialog"]
        build = ns["build_model"]
    else:
        from .modules.beam.builder import build_model
        domain = _static_domain(scope)
        if fast_mesh:
            _mesh_preview_facets(domain, 8)
        ns = domain.__dict__
        get_param = domain.parameter_dialog
        build = lambda: build_model(domain, progress=progress,
                                         dual_display=dual_display)
    ns["SPANS_M"] = [4.0] if mode == "single" else [4.0, 3.5, 4.5]
    ns["OUT_BASE"] = Path.home() / "GO_Engineering" / (
        "RC_Beam_Demo_v091_Phase2" if pipeline == "phase2" else "RC_Beam_Demo_v082")
    ns["SHOW_PARAMETER_DIALOG"] = True
    ns["VERIFY_SHOW_REPORT"] = True
    if not get_param():
        return {"accepted": False}
    if progress is not None:
        progress.report(12, "ตรวจพารามิเตอร์คาน / Beam parameters accepted")
    count = len(ns["SPANS_M"])
    if (mode == "single" and count != 1) or (mode == "multi" and count < 2):
        raise ValueError("Single Span requires 1 span; Continuous requires at least 2")
    from .adapters.ingetrazo.ifc import export_beam as export_beam_native
    from .native_ifc import require_native_bim
    require_native_bim()
    ns["export_beam_ifc"] = export_beam_native
    scene = ns["scene"]
    before = {id(g) for g in scene.groups}
    if pipeline == "accepted" and progress is not None:
        progress.report(35, "สร้างโมเดลคานแบบ Baseline / Building beam")
        # The locked legacy builder includes file output in one long call.
        # No safe checkpoint inside that call: forbid cancellation at entry.
        progress.commit()
    build()
    if pipeline == 'accepted' and dual_display:
        print('GO RC Dual Display: legacy Baseline has no saved centreline data; '
              'select Phase2 Beam Builder for native Wire/Solid layers.')
    if progress is not None:
        progress.report(95, "จัดเตรียม BIM / Preparing BIM group publication")
    if native_bim_visible:
        from .adapters.ingetrazo.scene import publish_native_bim
        candidates = [g for g in scene.groups if id(g) not in before and
                      '-RC Continuous Beam Assembly' in (g.name or '')]
        if len(candidates) != 1:
            raise ValueError("Expected exactly one new beam parent for Native BIM")
        result = publish_native_bim(scene, candidates[0], prefix=ns["BEAM_ID"])
        print("Native BIM objects published:", result["tagged"])
    if progress is not None:
        progress.commit()
        progress.report(100, "สร้างคานสำเร็จ / Beam model generated")
    print("GO RC beam pipeline:", pipeline,
          "| Mesh profile:", "8 facets (preview)" if fast_mesh else "12 facets (accepted)")
    return {"accepted": True, "beam_id": ns["BEAM_ID"], "spans": count,
            "pipeline": pipeline}
