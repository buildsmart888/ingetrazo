# SPDX-License-Identifier: GPL-3.0-or-later
"""Pixel checks of the actual instanced rebar line pass (requires OpenGL)."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QMatrix4x4, QVector3D as V
from PySide6.QtWidgets import QApplication

from core.group import Group
from core.rebar_display import attach_centerline
from scripts.GO_RB9_Stirrup_Fix import _make_group, build_beam, tube_mesh_data
from views.viewport import Viewport


@pytest.fixture
def viewport():
    vp = Viewport()
    vp.resize(800, 600)
    samples = [((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
               ((3.0, 0.0, 0.0), (1.0, 0.0, 0.0))]
    proto = _make_group(tube_mesh_data(samples, 0.22), "bar-definition",
                        (0.1, 0.3, 0.9, 1.0), "IfcReinforcingBar")
    for y in (-0.6, 0.6):
        g = Group(proto.mesh, name=f"bar-{y}")
        g.xform = QMatrix4x4()
        g.xform.translate(-1.5, y, 1.0)
        attach_centerline(g, [p for p, _ in samples], 0.22, "round-bar")
        vp.scene.groups.append(g)
    vp.scene.version += 1
    vp.camera.set_view("top")
    vp.camera.perspective = False
    vp.camera.fit_to(V(-2, -1.2, 0), V(2, 1.2, 1.2))
    vp.show()
    for _ in range(5):
        QApplication.processEvents()
    try:
        if getattr(vp, "_gl", None) is None or not vp.isValid():
            pytest.skip("no OpenGL context on this platform")
        yield vp
    finally:
        vp.close()


def _rgb(image):
    image = image.convertToFormat(QImage.Format_RGBA8888)
    raw = np.frombuffer(image.bits(), dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine())[:, :image.width() * 4]
    return raw.reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)


def _blue(image):
    rgb = _rgb(image)
    return (rgb[:, :, 2] > rgb[:, :, 0] + 35) & (rgb[:, :, 2] > rgb[:, :, 1] + 25)


def _blue_near(vp, mask, point):
    px, py = vp._world_to_pixel(point)
    scale = mask.shape[1] / vp.width()
    x, y = round(px * scale), round(py * scale)
    return mask[max(0, y - 3):y + 4, max(0, x - 3):x + 4].any()


def _patch_near(vp, rgb, point):
    px, py = vp._world_to_pixel(point)
    scale = rgb.shape[1] / vp.width()
    x, y = round(px * scale), round(py * scale)
    return rgb[y - 2:y + 3, x - 2:x + 3]


def test_actual_gl_draws_instances_as_lines_then_restores_solids(viewport, tmp_path):
    vp = viewport
    before = (vp.scene.version, vp.scene.content_version,
              tuple((g.uid, id(g.mesh), tuple(g.xform.data())) for g in vp.scene.groups))
    detailed_image = vp.grabFramebuffer()
    detailed = _blue(detailed_image)
    assert detailed.sum() > 500
    vp._last_pos = QPoint(10, 10)
    assert vp._rebar_lod_active()
    line_image = vp.grabFramebuffer()
    lines = _blue(line_image)
    assert 20 < lines.sum() < detailed.sum() * 0.3
    for y in (-0.6, 0.6):
        assert _blue_near(vp, lines, V(0, y, 1)), "each placement must be visible"
        # The first line frame must also remove the cached gray silhouette,
        # not only blue faces. Sample away from the centerline and axes.
        rgb = _rgb(line_image)
        old_outline = _patch_near(vp, rgb, V(0.8, y + 0.11, 1))
        background = _patch_near(vp, rgb, V(0.8, y + 0.22, 1))
        assert np.max(np.abs(old_outline - background)) <= 3
    # Pixel artifacts aid inspection if the driver exposes a rendering regression.
    detailed_image.save(str(tmp_path / "solid.png"))
    line_image.save(str(tmp_path / "centerline.png"))
    vp._end_camera_drag()
    restored = _blue(vp.grabFramebuffer())
    assert np.array_equal(restored, detailed)
    after = (vp.scene.version, vp.scene.content_version,
             tuple((g.uid, id(g.mesh), tuple(g.xform.data())) for g in vp.scene.groups))
    assert after == before


def test_actual_gl_preview_uses_the_moved_pose_and_export_keeps_solids(viewport):
    vp = viewport
    group = vp.scene.groups[0]
    vp.begin_groups_preview([group])
    vp.set_groups_preview_offset(V(0, 0.3, 0))
    moved = _blue(vp.grabFramebuffer())
    assert _blue_near(vp, moved, V(0, -0.3, 1))
    assert not _blue_near(vp, moved, V(0, -0.6, 1))
    # Exports use their own full-detail render even mid-gesture.
    exported = _blue(vp.render_image(800, 600, overlays=False))
    assert exported.sum() > moved.sum() * 3
    assert vp._rebar_lod_active()  # export did not change interaction/model state
    vp.end_groups_preview()


def test_actual_gl_complete_beam_shows_rebar_through_concrete(viewport, tmp_path):
    vp = viewport
    vp.scene.clear()
    build_beam(vp.scene, vp)
    vp.scene.version += 1
    vp.camera.perspective = True
    vp.camera.fit_to(*vp.scene.bounds())
    solid = vp.grabFramebuffer()
    assert _blue(solid).sum() > 100, "concrete must not hide the reinforcement"
    vp._last_pos = QPoint(10, 10)
    lines = vp.grabFramebuffer()
    assert _blue(lines).sum() > 100, "centrelines must remain visible through concrete"
    assert lines != solid
    assert len(vp._rebar_draw) == 3  # RB9 plus two coloured DB12 definitions
    solid.save(str(tmp_path / "beam-solid.png"))
    lines.save(str(tmp_path / "beam-lines.png"))
    vp._end_camera_drag()
    assert vp.grabFramebuffer() == solid
