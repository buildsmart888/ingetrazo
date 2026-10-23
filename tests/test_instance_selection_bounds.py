"""Selection boxes reuse local points, not baked copies of every bar."""
import numpy as np
import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D

from core.group import Group, oriented_box_corners
from core.history import History, MoveGroupCommand
from core.mesh import Mesh
from views.viewport import Viewport


@pytest.fixture
def instance_viewport(monkeypatch):
    vp = Viewport()
    mesh = Mesh()
    mesh.add_face([QVector3D(), QVector3D(2, 0, 0), QVector3D(2, 1, 3), QVector3D(0, 1, 3)])
    for index in range(3):
        group = Group(mesh)
        group.xform = QMatrix4x4()
        group.xform.translate(index * 5.0, 0, 0)
        vp.scene.groups.append(group)
    monkeypatch.setattr(vp, "_group_chunk", lambda g: pytest.fail("selection box baked a chunk"))
    yield vp
    vp.close()


def points(box):
    return np.asarray([p.toTuple() for p in oriented_box_corners(*box)])


@pytest.mark.parametrize("scale", [(1, 1, 1), (2, 3, 4), (-2, 1, 3)])
def test_instance_box_matches_exact_geometry_without_baking(instance_viewport, scale):
    vp = instance_viewport
    group = vp.scene.groups[0]
    group.xform.rotate(37, 0, 0, 1)
    group.xform.scale(*scale)
    assert points(vp._group_obb(group)) == pytest.approx(points(vp._compute_obb(group)))
    group.axes = QMatrix4x4()
    group.axes.rotate(21, 0, 1, 0)
    assert points(vp._group_obb(group)) == pytest.approx(points(vp._compute_obb(group)))


def test_selection_reuses_bounds_and_shared_local_points(instance_viewport):
    vp = instance_viewport
    group, sibling = vp.scene.groups[:2]
    first = vp._group_obb(group)
    local = vp._proto_pts_store[id(group.mesh)][1]
    for selected in ([group], [sibling], [], [group, sibling]):
        vp.scene.select(selected)
        assert vp._group_obb(group) is first
    vp._group_obb(sibling)
    assert vp._proto_pts_store[id(group.mesh)][1] is local


def test_move_undo_mesh_mutation_and_axes_invalidate_bounds(instance_viewport):
    vp = instance_viewport
    group = vp.scene.groups[0]
    first = vp._group_obb(group)
    history = History(vp.scene)
    history.execute(MoveGroupCommand(group, QVector3D(7, 3, 0)))
    assert vp._group_obb(group) is not first
    assert points(vp._group_obb(group)) == pytest.approx(points(vp._compute_obb(group)))
    assert history.undo()
    assert points(vp._group_obb(group)) == pytest.approx(points(first))
    vertex = group.mesh.vertices[0]
    group.mesh.move_vertex(vertex, QVector3D(-5, 0, 0))
    changed = vp._group_obb(group)
    assert points(changed) == pytest.approx(points(vp._compute_obb(group)))
    group.axes = QMatrix4x4()
    group.axes.rotate(45, 0, 0, 1)
    assert vp._group_obb(group) is not changed
    assert points(vp._group_obb(group)) == pytest.approx(points(vp._compute_obb(group)))


def test_ten_thousand_selection_boxes_keep_one_prototype_array(instance_viewport):
    vp = instance_viewport
    prototype = vp.scene.groups[0].mesh
    vp.scene.groups.clear()
    for index in range(10000):
        group = Group(prototype)
        group.xform = QMatrix4x4()
        group.xform.translate(float(index % 100), float(index // 100), 0.0)
        vp.scene.groups.append(group)
        vp._group_obb(group)
    assert len(vp._proto_pts_store) == 1
    assert len(vp._placement_obb) == 10000
    first = vp._group_obb(vp.scene.groups[0])
    vp.scene.select(vp.scene.groups)
    assert vp._group_obb(vp.scene.groups[0]) is first
