# SPDX-License-Identifier: GPL-3.0-or-later
"""Selecting objects must not traverse the model again for its extents."""
from PySide6.QtGui import QMatrix4x4, QVector3D

from core.group import Group
from core.history import HideCommand, History, MoveGroupCommand
from core.mesh import Mesh
from core.scene import Scene


def _scene():
    mesh = Mesh()
    mesh.add_face([QVector3D(0, 0, 0), QVector3D(2, 0, 0),
                   QVector3D(2, 1, 0), QVector3D(0, 1, 0)])
    group = Group(mesh)
    group.xform = QMatrix4x4()
    scene = Scene(groups=[group])
    return scene, group


def _bounds(scene):
    return tuple(None if p is None else (p.x(), p.y(), p.z()) for p in scene.bounds())


def test_selecting_and_deselecting_reuses_extents_without_walking_instances(monkeypatch):
    scene, group = _scene()
    original = Scene.placements
    walks = []

    def counted(self):
        walks.append(self)
        yield from original(self)

    monkeypatch.setattr(Scene, "placements", counted)
    expected = _bounds(scene)
    for mode in ("replace", "add", "toggle", "remove"):
        scene.select([group], mode=mode)
        assert _bounds(scene) == expected
    scene.select([group])
    scene.clear_selection()
    assert _bounds(scene) == expected
    assert len(walks) == 1


def test_move_undo_hide_and_unhide_update_extents():
    scene, group = _scene()
    history = History(scene)
    initial = _bounds(scene)
    history.execute(MoveGroupCommand(group, QVector3D(5, 2, 3)))
    assert _bounds(scene) == ((5.0, 2.0, 3.0), (7.0, 3.0, 3.0))
    history.undo()
    assert _bounds(scene) == initial
    history.execute(HideCommand([group]))
    assert _bounds(scene) == (None, None)
    history.undo()
    assert _bounds(scene) == initial


def test_clear_and_repopulate_do_not_reuse_previous_document_extents():
    scene, group = _scene()
    assert _bounds(scene)[0] is not None
    scene.clear()
    assert _bounds(scene) == (None, None)
    scene.add_edge(QVector3D(10, 0, 0), QVector3D(15, 1, 2))
    assert _bounds(scene) == ((10.0, 0.0, 0.0), (15.0, 1.0, 2.0))


def test_group_edit_and_return_keep_world_extents():
    scene, group = _scene()
    group.xform.translate(5.0, 0.0, 0.0)
    initial = _bounds(scene)
    scene.begin_group_edit(group)
    assert _bounds(scene) == initial
    scene.end_group_edit()
    assert _bounds(scene) == initial
