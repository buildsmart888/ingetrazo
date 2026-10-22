# SPDX-License-Identifier: GPL-3.0-or-later
"""Display proxies preserve the solid and stop doing work for every instance."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QMatrix4x4, QVector3D as V

from core.group import Group
from core.mesh import Mesh
from core.rebar_display import CenterlineCache, attach_centerline, mesh_signature


def bar(mesh=None, offset=0.0):
    if mesh is None:
        mesh = Mesh()
        mesh.add_face([V(0, 0, 0), V(1, 0, 0), V(1, 0.1, 0)])
    g = Group(mesh, name="bar")
    g.xform = QMatrix4x4()
    g.xform.translate(offset, 0.0, 0.0)
    attach_centerline(g, [(0, 0, 0), (1, 0, 0)], 0.009, "RB9")
    return g


def mock_shader(viewport):
    viewport._program = Mock()
    for i, name in enumerate(("use_tex", "use_vcolor", "opacity", "shade", "fade",
                              "color", "back_color", "mvp")):
        setattr(viewport, "_loc_" + name, i)


@pytest.fixture
def viewport():
    from views.main_window import MainWindow
    window = MainWindow()
    yield window.viewport
    window._saved_version = window.viewport.scene.version
    window.close()


def test_signature_survives_reordered_faces_but_follows_shape_edit():
    g = bar()
    other = Mesh()
    other.add_face([V(1, 0.1, 0), V(1, 0, 0), V(0, 0, 0)])
    assert mesh_signature(g.mesh) == mesh_signature(other)
    cache = CenterlineCache()
    assert cache.get(g) is not None
    g.mesh.move_vertex(g.mesh.vertices[0], V(0, 0, 0.2))
    assert cache.get(g) is None


@pytest.mark.parametrize("bad", [None, [], {}, 5, "not-the-shape"])
def test_malformed_or_stale_proxy_falls_back_to_solid(bad):
    g = bar()
    g.ext["go_rebar"]["mesh_signature"] = bad
    assert CenterlineCache().get(g) is None


def test_selection_reuses_validated_line_and_mesh_edit_invalidates(viewport):
    g = bar()
    viewport.scene.groups.append(g)
    first = viewport._rebar_proxy(g)
    assert first is not None
    viewport.scene.select([g])
    assert viewport._rebar_proxy(g) is first
    # A producer that replaces its metadata is also respected before the
    # scene event; a parametric rebuild never shows the previous line.
    attach_centerline(g, [(0, 0, 0), (0.5, 0, 0), (1, 0, 0)], 0.009, "RB9")
    assert viewport._rebar_proxy(g)[0] != first[0]
    g.mesh.move_vertex(g.mesh.vertices[0], V(0, 0, 0.2))
    assert viewport._rebar_proxy(g) is None


def test_camera_interaction_filters_only_valid_rebar_without_document_changes(viewport):
    g, ordinary = bar(), bar(offset=2)
    ordinary.ext = None
    viewport.scene.groups.extend([g, ordinary])
    before = (viewport.scene.version, viewport.scene.content_version,
              list(g.mesh.vertices), list(g.mesh.faces), g.hidden, g.xform.data())
    assert viewport._rebar_solid_groups([g, ordinary]) == [g, ordinary]
    viewport._last_pos = QPoint(10, 10)
    assert viewport._rebar_solid_groups([g, ordinary]) == [ordinary]
    viewport._export_size = (1200, 800)
    assert viewport._rebar_solid_groups([g, ordinary]) == [g, ordinary]
    viewport._export_size = None
    viewport._end_camera_drag()
    assert viewport._rebar_solid_groups([g, ordinary]) == [g, ordinary]
    after = (viewport.scene.version, viewport.scene.content_version,
             list(g.mesh.vertices), list(g.mesh.faces), g.hidden, g.xform.data())
    assert after == before


def test_wheel_idle_focus_and_edit_context_restore_solids(viewport):
    g = bar()
    viewport._rebar_wheel_started()
    assert viewport._rebar_lod_active()
    viewport._rebar_wheel_idle()
    assert not viewport._rebar_lod_active()


def test_transform_preview_and_edit_context_restore_solids(viewport):
    g = bar()
    viewport._preview_groups = {id(g)}
    assert viewport._rebar_lod_active()
    viewport._rebar_lod_suspended = True
    assert not viewport._rebar_lod_active()
    viewport._rebar_lod_suspended = False
    viewport.scene.edit_group = g
    assert not viewport._rebar_lod_active()
    viewport.scene.edit_group = None
    viewport.end_groups_preview()
    assert not viewport._rebar_lod_active()


def test_focus_loss_clears_camera_gestures_even_if_release_is_lost(viewport):
    viewport._last_pos = QPoint(12, 12)
    viewport._look_drag = (Qt.LeftButton, QPoint(12, 12))
    viewport._rebar_wheel_started()
    viewport.focusOutEvent(QFocusEvent(QEvent.FocusOut))
    assert viewport._last_pos is None
    assert viewport._look_drag is None
    assert not viewport._rebar_lod_active()


def test_a_shared_proxy_batches_all_instances_in_one_line_draw(viewport, monkeypatch):
    from views.viewport import GL_LINES
    g = bar()
    groups = [g] + [bar(g.mesh, float(i)) for i in range(1, 40)]
    viewport.scene.groups.extend(groups)
    viewport._last_pos = QPoint(10, 10)
    gl = Mock()
    monkeypatch.setattr(viewport, "context", lambda: SimpleNamespace(extraFunctions=lambda: gl))
    mock_shader(viewport)
    entry = {"lines_vao": Mock(), "mat_vbo": Mock(), "mat_sig": None, "count": 2}
    monkeypatch.setattr(viewport, "_ensure_rebar_draw", lambda mesh, proxy: entry)
    batches = {"bar": (g.mesh, None, groups, False)}
    viewport._draw_rebar_centerlines(batches)
    viewport._draw_rebar_centerlines(batches)
    assert gl.glDrawArraysInstanced.call_count == 2  # one batch per frame
    assert gl.glDrawArraysInstanced.call_args.args == (GL_LINES, 0, 2, 40)
    assert entry["mat_vbo"].allocate.call_count == 1  # matrices unchanged


def test_centerline_mode_does_not_submit_solid_faces_or_edges(viewport, monkeypatch):
    g = bar()
    viewport._last_pos = QPoint(10, 10)
    mock_shader(viewport)
    viewport._gl = Mock()
    monkeypatch.setattr(viewport, "context", lambda: SimpleNamespace(extraFunctions=Mock()))
    monkeypatch.setattr(viewport, "_ensure_proto_draw", Mock(side_effect=AssertionError(
        "A simplified bar must not submit its solid mesh")))
    batches = {"bar": (g.mesh, None, [g], False)}
    viewport._draw_instanced_faces("shaded", viewport._effective_style(), batches)
    viewport._draw_instanced_edges(batches)


def test_select_context_avoids_work_plane_ray_but_other_tools_keep_it(viewport, monkeypatch):
    from tools.select import SelectTool
    viewport.active_tool = SelectTool()
    event = SimpleNamespace(position=lambda: QPointF(25, 35), modifiers=lambda: Qt.NoModifier)
    project = Mock(side_effect=AssertionError("Select does not need a construction plane"))
    monkeypatch.setattr(viewport, "_world_from_pixel", project)
    context = viewport._build_ctx(event)
    assert context.screen == QPointF(25, 35)
    assert context.snap.kind == "none"
    project.assert_not_called()
    viewport.active_tool = SimpleNamespace(uses_snap=False, screen_context_only=False)
    project.side_effect = None
    project.return_value = V(1, 2, 3)
    assert viewport._build_ctx(event).world == V(1, 2, 3)
    project.assert_called_once()


def test_move_preview_freezes_instances_without_baking_faces(viewport, monkeypatch):
    g = bar(offset=2)
    viewport.scene.groups.append(g)
    chunk = viewport._group_chunk

    def no_world_bake(group):
        assert group is not g, "A rebar drag must not bake the moving solid"
        return chunk(group)

    monkeypatch.setattr(viewport, "_group_chunk", no_world_bake)
    monkeypatch.setattr(viewport, "makeCurrent", Mock())
    monkeypatch.setattr(viewport, "doneCurrent", Mock())
    for name in ("_create_dynamic", "_create_dynamic_vcol", "_create_dynamic_uv"):
        monkeypatch.setattr(viewport, name, lambda: (Mock(), Mock()))
    mock_shader(viewport)
    viewport._gl = Mock()
    monkeypatch.setattr(viewport, "context", lambda: SimpleNamespace(extraFunctions=Mock()))
    before = viewport.scene.content_version
    viewport.begin_groups_preview([g])
    assert viewport._pv_vcol_count == viewport._pv_edges_count == 0
    frozen = next(iter(viewport._pv_rebar_proto.values()))[2][0]
    assert frozen.mesh is g.mesh
    original = list(frozen.xform.data())
    g.xform.translate(7.0, 0.0, 0.0)
    assert list(frozen.xform.data()) == original
    viewport.set_groups_preview_offset(V(3, 0, 0))
    lines = Mock()
    monkeypatch.setattr(viewport, "_draw_rebar_centerlines", lines)
    viewport._draw_groups_preview(QMatrix4x4())
    lines.assert_called_once_with(viewport._pv_rebar_proto)
    # An edited shared mesh no longer matches its proxy. It must be sent
    # through the solid pass at the frozen preview pose, never disappear.
    entry = {"mat_vbo": Mock(), "mat_sig": None, "vcol_count": 3,
             "vcol_vao": Mock(), "tex_runs": [], "edge_count": 0}
    solid = Mock(return_value=entry)
    monkeypatch.setattr(viewport, "_ensure_proto_draw", solid)
    g.mesh.move_vertex(g.mesh.vertices[0], V(0, 0, 0.2))
    viewport._draw_groups_preview(QMatrix4x4())
    assert solid.call_count > 0
    # A suspended interaction still draws the solid at the preview pose.
    viewport._rebar_lod_suspended = True
    faces, edges = Mock(), Mock()
    monkeypatch.setattr(viewport, "_draw_instanced_faces", faces)
    monkeypatch.setattr(viewport, "_draw_instanced_edges", edges)
    viewport._draw_groups_preview(QMatrix4x4())
    assert faces.call_args.args[2] is viewport._pv_rebar_proto
    assert edges.call_args.args[0] is viewport._pv_rebar_proto
    viewport.end_groups_preview()
    assert not viewport._pv_rebar_proto
    assert viewport.scene.content_version == before


def test_proxy_gpu_cache_releases_deleted_and_rebuilt_definitions(viewport, monkeypatch):
    a, b = bar(), bar(offset=2)
    viewport.scene.groups.extend([a, b])
    ka = (id(a.mesh), viewport._rebar_proxy(a)[0])
    kb = (id(b.mesh), viewport._rebar_proxy(b)[0])
    ea, eb = {"mesh": a.mesh}, {"mesh": b.mesh}
    viewport._rebar_draw = {ka: ea, kb: eb}
    destroy = Mock()
    monkeypatch.setattr(viewport, "_destroy_proto_draw_entry", destroy)
    viewport._prune_rebar_draw()
    destroy.assert_not_called()
    viewport.scene.groups.remove(a)
    viewport.scene.version += 1
    viewport._prune_rebar_draw()
    destroy.assert_called_once_with(ea)
    assert viewport._rebar_draw == {kb: eb}
    # A centreline rebuild changes the draw key even when its mesh is reused.
    attach_centerline(b, [(0, 0, 0), (0.5, 0, 0), (1, 0, 0)], 0.009, "RB9")
    viewport.scene.version += 1
    viewport._prune_rebar_draw()
    assert destroy.call_args.args == (eb,)
    assert not viewport._rebar_draw
