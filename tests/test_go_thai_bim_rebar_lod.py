# SPDX-License-Identifier: GPL-3.0-or-later
"""GO/Thai BIM solid rebar must feed the host's verified line-LOD contract."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QMatrix4x4

from core.extensions import _import_by_path
from core.rebar_display import describe_centerline, mesh_signature


@pytest.fixture(scope="module")
def thai_bim():
    path = Path(__file__).resolve().parents[1] / "plugins" / "thai_bim" / "__init__.py"
    stem = "thai_bim_rebar_lod_test"
    module = _import_by_path(stem, path)
    yield module
    prefix = "ingetrazo_plugin_" + stem
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
        sys.modules.pop(name, None)


def _detailing(module):
    return importlib.import_module(module.__name__ + ".detailing")


@pytest.mark.parametrize("representation", ["Full", "Lightweight"])
def test_go_solid_rebar_attaches_verified_local_centerline(thai_bim, representation):
    detailing = _detailing(thai_bim)
    spec = detailing.bent_bar(
        "tie-1",
        [(0.02, 0.04, 0.04), (0.02, 0.18, 0.04),
         (0.02, 0.18, 0.36), (0.02, 0.02, 0.36)],
        0.009,
        inside_radius=0.018,
        shape="Tie-test",
        representation=representation,
    )
    group = thai_bim.make_group(spec)
    metadata = group.ext["go_rebar"]

    assert group.ext["thai_bim"]["bar_path"] == spec["bar_path"]
    assert metadata["centerline"] == [list(p) for p in spec["bar_path"]]
    assert metadata["diameter_m"] == pytest.approx(0.009)
    assert metadata["definition_key"] == spec["bbs"]["mark"]
    assert metadata["mesh_signature"] == mesh_signature(group.mesh)

    # reconcile_specs applies the host pose after make_group. An identity pose
    # is enough to establish the same component/placement contract here.
    group.xform = QMatrix4x4()
    info = describe_centerline(group)
    assert info["status"] == "ready"
    assert info["reason"] == "verified"
    assert info["points"] == len(spec["bar_path"])


def test_go_centreline_representation_remains_native_wire_not_lod_proxy(thai_bim):
    detailing = _detailing(thai_bim)
    spec = detailing.bent_bar(
        "wire-1", [(0, 0, 0), (1, 0, 0)], 0.012,
        representation="Centreline",
    )
    group = thai_bim.make_group(spec)
    assert "go_rebar" not in group.ext
    assert len(group.mesh.faces) == 0
    assert len(group.mesh.edges) == 1


def test_go_rebar_regeneration_replaces_old_signature_and_keeps_pose(thai_bim):
    detailing = _detailing(thai_bim)
    first_spec = detailing.bent_bar(
        "main-1", [(0, 0, 0), (1, 0, 0)], 0.012, representation="Full")
    first = thai_bim.make_group(first_spec)
    first.xform = QMatrix4x4()
    first.xform.translate(4.0, 2.0, 1.0)
    old_signature = first.ext["go_rebar"]["mesh_signature"]

    second_spec = detailing.bent_bar(
        "main-1", [(0, 0, 0), (1.5, 0, 0)], 0.012, representation="Full")
    second = thai_bim.make_group(second_spec, previous=first)

    assert second.uid == first.uid
    assert list(second.xform.data()) == pytest.approx(list(first.xform.data()))
    assert second.ext["go_rebar"]["mesh_signature"] == mesh_signature(second.mesh)
    assert second.ext["go_rebar"]["mesh_signature"] != old_signature
    assert second.ext["go_rebar"]["centerline"] == [list(p) for p in second_spec["bar_path"]]
