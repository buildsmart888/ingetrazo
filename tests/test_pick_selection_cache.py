# SPDX-License-Identifier: GPL-3.0-or-later
"""Selection-only changes reuse geometry; edits and lazy membership do not."""
import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D as V

from core.group import Group
from core.history import HideCommand, History, MoveGroupCommand
from core.layers import Layer
from core.mesh import Mesh
from views.viewport import Viewport


@pytest.fixture
def viewport():
    vp = Viewport()
    vp.resize(800, 600)
    proto = Mesh()
    proto.add_face([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0), V(0, 1, 0)])
    for i in range(3):
        g = Group(proto, name=f"bar-{i}")
        g.xform = QMatrix4x4()
        g.xform.translate(float(i * 3), 0.0, 0.0)
        vp.scene.groups.append(g)
    vp.scene.version += 1
    yield vp
    vp.close()


def test_selection_reuses_arrays_and_still_returns_the_same_object(viewport):
    vp = viewport
    vp._pixel_to_ray = lambda x, y: (V(0.5, 0.5, 10), V(0, 0, -1))
    initial = vp._pick_index(near="all")
    assert vp.pick_group(0, 0) is vp.scene.groups[0]
    for mode in ("replace", "add", "toggle", "remove"):
        vp.scene.select([vp.scene.groups[0]], mode=mode)
        assert vp._pick_index(near="all") is initial
        assert vp.pick_group(0, 0) is vp.scene.groups[0]


def test_transform_and_undo_invalidate_pick_geometry(viewport):
    vp = viewport
    vp._pixel_to_ray = lambda x, y: (V(0.5, 0.5, 10), V(0, 0, -1))
    group = vp.scene.groups[0]
    initial = vp._pick_index(near="all")
    history = History(vp.scene)
    history.execute(MoveGroupCommand(group, V(0, 5, 0)))
    assert vp._pick_index(near="all") is not initial
    assert vp.pick_group(0, 0) is None
    history.undo()
    assert vp.pick_group(0, 0) is group


def test_hide_and_layer_lock_change_selectability(viewport):
    vp = viewport
    vp._pixel_to_ray = lambda x, y: (V(0.5, 0.5, 10), V(0, 0, -1))
    group = vp.scene.groups[0]
    history = History(vp.scene)
    assert vp.pick_group(0, 0) is group
    history.execute(HideCommand([group]))
    assert vp.pick_group(0, 0) is None
    history.undo()
    assert vp.pick_group(0, 0) is group
    layer = Layer("Rebar")
    vp.scene.layers.append(layer)
    group.layer = layer.name
    layer.locked = True
    vp.scene.version += 1
    assert vp.pick_group(0, 0) is None
    layer.locked = False
    vp.scene.version += 1
    assert vp.pick_group(0, 0) is group


def test_open_component_changes_pick_owner_and_context(viewport):
    vp = viewport
    group = vp.scene.groups[0]
    initial = vp._pick_index(near="all")
    vp.scene.begin_group_edit(group)
    inside = vp._pick_index(near="all")
    assert inside is not initial
    assert any(f in group.mesh.faces and owner is None for f, owner in inside.entities)
    vp.scene.end_group_edit()
    assert vp._pick_index(near="all") is not inside


def test_lazy_membership_still_invalidates_after_a_selection(viewport):
    vp = viewport
    vp._PICK_LAZY_MIN_FACES = 1
    vp._PICK_LIVE_MAX_FACES = 1
    first_query = ("ray", V(0.5, 0.5, 10), V(0, 0, -1))
    second_query = ("ray", V(6.5, 0.5, 10), V(0, 0, -1))
    first = vp._pick_index(near=first_query)
    vp.scene.select([vp.scene.groups[0]])
    assert vp._pick_index(near=first_query) is first
    second = vp._pick_index(near=second_query)
    assert second is not first
    assert any(owner is vp.scene.groups[2] for _, owner in second.entities)
