# SPDX-License-Identifier: GPL-3.0-or-later
"""The RB9 console demo stores one shape per definition, not per placement."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QVector3D

from core.group import Group
from core.scene import Scene
from formats import igz


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "GO_RB9_Stirrup_Fix.py"
_SPEC = importlib.util.spec_from_file_location("rb9_component_demo", _SCRIPT)
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)


@pytest.fixture(scope="module")
def beam():
    scene = Scene()
    result = demo.build_beam(scene)
    return scene, result


def _stirrups(scene):
    return [g for g in scene.groups if g.name.startswith(demo.PREFIX + "RB9_")]


def _coords(point):
    return point.x(), point.y(), point.z()


def test_one_stirrup_definition_keeps_nineteen_independent_objects(beam):
    scene, result = beam
    stirrups = _stirrups(scene)
    assert len(stirrups) == 19
    assert len({id(g.mesh) for g in stirrups}) == 1
    assert all(g.is_component() for g in stirrups)
    assert len({g.uid for g in scene.groups}) == 25
    assert len({id(g.ifc) for g in stirrups}) == 19
    assert len({id(g.ext) for g in stirrups}) == 19
    assert len({id(g.ext["go_rebar"]) for g in stirrups}) == 1
    assert len({g.name for g in stirrups}) == 19
    assert all(g.ifc == {"class": "IfcReinforcingBar", "name": g.name}
               for g in stirrups)
    assert result["groups_created"] == 25
    assert result["stirrups"] == 19
    assert result["triangles"] == 41676
    assert result["unique_meshes"] == 4
    assert result["unique_mesh_faces"] == 2316
    assert result["boundary_edges"] == 0


def test_straight_bars_share_by_colour_and_have_local_centerlines(beam):
    scene, _ = beam
    for label, positions, colour in (
            ("DB12_Top", demo.TOP_BARS_YZ, (0.9, 0.2, 0.2, 1.0)),
            ("DB12_Bottom", demo.BOTTOM_BARS_YZ, (0.9, 0.5, 0.1, 1.0))):
        groups = [g for g in scene.groups if g.name.startswith(demo.PREFIX + label)]
        assert len(groups) == len(positions)
        assert len({id(g.mesh) for g in groups}) == 1
        assert all(g.is_component() for g in groups)
        for group, (y, z) in zip(groups, positions):
            assert group.ext["go_rebar"]["centerline"] == [
                [0.0, 0.0, 0.0], [demo.BEAM_LENGTH, 0.0, 0.0]]
            assert group.ext["go_rebar"]["diameter_m"] == demo.LONGITUDINAL_DIAMETER
            assert _coords(group.xform.map(QVector3D())) == pytest.approx((0, y, z))
            assert all(f.attrs["color"] == colour[:3] for f in group.mesh.faces)
            assert all(f.attrs["opacity"] == colour[3] for f in group.mesh.faces)


def test_concrete_is_translucent_and_rebar_stays_opaque(beam):
    from core.materials import is_translucent

    scene, _ = beam
    concrete = next(g for g in scene.groups if g.ifc["class"] == "IfcBeam")
    assert all(f.attrs["color"] == (0.85, 0.85, 0.85) for f in concrete.mesh.faces)
    assert all(f.attrs["opacity"] == demo.CONCRETE_ALPHA for f in concrete.mesh.faces)
    assert all(is_translucent(f.attrs) for f in concrete.mesh.faces)
    for group in scene.groups:
        if group.ifc["class"] == "IfcReinforcingBar":
            assert all(len(f.attrs["color"]) == 3 and f.attrs["opacity"] == 1.0
                       for f in group.mesh.faces)
            assert not any(is_translucent(f.attrs) for f in group.mesh.faces)


def test_placed_stirrup_faces_match_the_previous_world_geometry(beam):
    """Matrix placement preserves every bent-hook face, including the 3D jog."""
    scene, _ = beam
    for group, x in zip(_stirrups(scene), demo.stirrup_positions()):
        expected = demo.tube_mesh_data(demo.stirrup_path(x), demo.STIRRUP_DIAMETER)
        expected_faces = np.asarray([
            [expected["vertices"][index] for index in face]
            for face in expected["faces"]
        ])
        placed_faces = np.asarray([
            [_coords(group.xform.map(point)) for point in face.vertices]
            for face in group.mesh.faces
        ])
        # Qt's vectors and matrices store float32; local->world rounds one
        # extra time compared with constructing a world-coordinate vector.
        np.testing.assert_allclose(placed_faces, expected_faces, rtol=0, atol=3e-7)


def test_all_unique_meshes_are_closed_with_positive_volume(beam):
    from core.bim import face_set_volume

    scene, _ = beam
    for mesh in {id(g.mesh): g.mesh for g in scene.groups}.values():
        assert all(len(edge.faces) == 2 for edge in mesh.edges)
        assert face_set_volume(mesh.faces) > 0


def test_rerun_replaces_only_its_objects_and_drops_stale_selection():
    scene = Scene()
    unrelated = Group(name="Existing project object")
    scene.groups.append(unrelated)
    demo.build_beam(scene)
    old = set(_stirrups(scene))
    scene.selection.update([unrelated, next(iter(old))])
    result = demo.build_beam(scene)
    assert len(scene.groups) == 26
    assert scene.groups[0] is unrelated
    assert not old.intersection(scene.groups)
    assert scene.selection == {unrelated}
    assert len({layer.name for layer in scene.layers}) == len(scene.layers)
    assert result["unique_meshes"] == 4


def test_native_roundtrip_keeps_shared_prototypes_identity_and_centerlines(beam, tmp_path):
    scene, _ = beam
    path = tmp_path / "rb9-shared.igz"
    igz.save_scene(scene, path)
    loaded = Scene()
    igz.load_into(loaded, path)
    assert len(loaded.groups) == 25
    assert len({id(g.mesh) for g in _stirrups(loaded)}) == 1
    for original, restored in zip(scene.groups, loaded.groups):
        assert restored.name == original.name
        assert restored.uid == original.uid
        assert restored.ifc == original.ifc
        assert restored.ext == original.ext
        assert len(restored.mesh.faces) == len(original.mesh.faces)
        for before, after in zip(original.mesh.faces, restored.mesh.faces):
            assert tuple(after.attrs["color"]) == before.attrs["color"]
            assert after.attrs["opacity"] == before.attrs["opacity"]
        if original.xform is not None:
            assert restored.is_component()
            assert list(restored.xform.data()) == pytest.approx(list(original.xform.data()))


def test_native_roundtrip_centerline_signature_still_matches_mesh(beam, tmp_path):
    from core.rebar_display import mesh_signature

    scene, _ = beam
    path = tmp_path / "rb9-lod.igz"
    igz.save_scene(scene, path)
    loaded = Scene()
    igz.load_into(loaded, path)
    for group in loaded.groups:
        if group.ifc["class"] == "IfcReinforcingBar":
            metadata = group.ext["go_rebar"]
            assert metadata["version"] == 1
            assert metadata["mesh_signature"] == mesh_signature(group.mesh)


def test_moving_one_instance_preserves_shared_vertices_and_other_placements(beam):
    from core.group import copy_group

    scene, _ = beam
    first, second = _stirrups(scene)[:2]
    vertices_before = [_coords(v.position) for v in first.mesh.vertices]
    second_pose = list(second.xform.data())
    moved = copy_group(first, QVector3D(0.25, 0.05, 0))
    assert moved.mesh is first.mesh
    assert moved.uid != first.uid
    assert [_coords(v.position) for v in first.mesh.vertices] == vertices_before
    assert list(second.xform.data()) == second_pose
    assert _coords(moved.xform.map(QVector3D())) == pytest.approx(
        (demo.FIRST_STIRRUP + 0.25, 0.05, 0))
