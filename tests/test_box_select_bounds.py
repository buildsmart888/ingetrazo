"""A box around repeated bars must not materialize all their geometry."""
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D

from core.group import Group
from core.mesh import Mesh
from tools.select import _box_group_bounds, _box_group_fast


def placed(lo=(1, 1, 1), hi=(2, 2, 2)):
    mesh = Mesh()
    mesh.add_face([QVector3D(*lo), QVector3D(hi[0], lo[1], lo[2]), QVector3D(*hi)])
    group = Group(mesh)
    group.xform = QMatrix4x4()
    return group


def viewport(bounds):
    def no_bake(_group):
        pytest.fail("decisive bounds must not bake placed triangle/edge chunks")

    def project(points):
        return points[:, 0], points[:, 1], np.ones(len(points), dtype=bool)

    return SimpleNamespace(_placement_bbox=lambda group: bounds[group],
                           _project_px=project, _group_chunk=no_bake)


@pytest.mark.parametrize("crossing", [False, True])
@pytest.mark.parametrize("bounds,expected", [
    (((1, 1, 1), (2, 2, 2)), True),
    (((8, 8, 1), (10, 10, 2)), False),
])
def test_decisive_bounds_do_not_materialize(crossing, bounds, expected):
    group = placed()
    vp = viewport({group: bounds})
    assert _box_group_fast(vp, group, (0, 0, 5, 5), crossing) is expected


@pytest.mark.parametrize("crossing", [False, True])
def test_partial_overlap_and_box_surrounding_cursor_are_not_hits(crossing):
    group = placed()
    # An empty rectangular frame could surround the cursor without touching it.
    vp = viewport({group: ((-10, -10, 1), (10, 10, 2))})
    assert _box_group_bounds(vp, [group], (0, 0, 5, 5), crossing) is None


def test_nested_placements_keep_window_and_crossing_semantics():
    a, b = placed(), placed()
    vp = viewport({a: ((1, 1, 1), (2, 2, 2)), b: ((8, 8, 1), (9, 9, 2))})
    assert _box_group_bounds(vp, [a, b], (0, 0, 5, 5), False) is False
    assert _box_group_bounds(vp, [a, b], (0, 0, 5, 5), True) is True


def test_near_plane_and_unknown_transform_retain_exact_test():
    group = placed()
    vp = viewport({group: ((1, 1, -1), (2, 2, 1))})
    vp._project_px = lambda p: (p[:, 0], p[:, 1], p[:, 2] > 0)
    assert _box_group_bounds(vp, [group], (0, 0, 5, 5), True) is None
    group.xform = None
    assert _box_group_bounds(vp, [group], (0, 0, 5, 5), False) is None
