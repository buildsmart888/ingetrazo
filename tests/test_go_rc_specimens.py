"""Real plugin geometry and persistence exercise the selection cache contract."""
from collections import Counter
from copy import deepcopy

import pytest
from PySide6.QtGui import QVector3D

from core import bim
from core.history import History, MoveGroupCommand
from core.scene import Scene
from formats.igz import load_into
from scripts.rc_specimens import plugin_module, run, solid_snapshot


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    output = tmp_path_factory.mktemp("rc-replay") / "specimens"
    report = run(output)
    return output, report


@pytest.fixture
def specimen_scene(replay):
    scene = Scene()
    load_into(scene, replay[0] / "four-rc-specimens.igz")
    return scene


def test_four_specimen_acceptance_and_persistence(replay):
    _, report = replay
    assert all(report["acceptance"].values()), report["acceptance"]
    assert report["bar_count"] == 181
    assert report["bar_prototypes"] == 20
    assert report["wire"]["assemblies"] == 4
    assert report["wire"]["bars"] == 181
    assert report["wire"]["missing_legacy_bars"] == 0
    assert report["bim_selection"]["bim_rows"] == 204


@pytest.mark.parametrize("identifier,bars,ties", [
    ("QA_SB", 40, 29), ("QA_CB", 107, 88), ("QA_CR", 25, 21), ("QA_CC", 9, 1),
])
def test_specimen_dimensions_quantities_and_native_ids(replay, specimen_scene, identifier, bars, ties):
    row = next(row for row in replay[1]["specimens"] if row["id"] == identifier)
    assert row["bars"] == bars
    assert row["ties"] == ties
    assert row["mass_kg"] > 0
    if row["kind"] == "beam":
        assert row["section_mm"] == [300, 500]
        assert row["verification_issues"] == 0
    else:
        assert row["height_mm"] == 3000
    snapshot = solid_snapshot(specimen_scene)
    members = [bar for bar in snapshot["bars"] if bar["name"].startswith(identifier + "-")]
    assert len(members) == bars
    assert len({bar["uid"] for bar in members}) == bars
    assert sum(bar["metadata"]["weight_kg"] for bar in members) == pytest.approx(row["mass_kg"])
    assert all(bar["metadata"]["length_m"] > 0 for bar in members)
    concrete = [g for g in specimen_scene.groups
                if g.name.startswith(identifier + "-Concrete")]
    expected_lengths = row.get("spans_m", [3.0])
    assert len(concrete) == len(expected_lengths)
    for group, length in zip(concrete, expected_lengths):
        points = [v.position.toTuple() for v in group.mesh.vertices]
        extents = [max(p[axis] for p in points) - min(p[axis] for p in points)
                   for axis in range(3)]
        if row["kind"] == "beam":
            assert extents == pytest.approx([length, 0.3, 0.5], abs=1e-6)
        else:
            width = 0.3 if row["shape"] == "rect" else 0.4
            assert extents == pytest.approx([width, 0.4, 3.0], abs=1e-6)


def test_wire_modes_do_not_duplicate_ifc_quantities_or_rebuild_solids(specimen_scene):
    scene = specimen_scene
    display = plugin_module("dual_display")
    bars = [g for g in scene.groups if (g.ifc or {}).get("class") == "IfcReinforcingBar"]
    before = solid_snapshot(scene)
    meshes = [g.mesh for g in bars]
    expected = Counter(obj["class"] for obj in bim.collect_objects(scene))
    for mode in ("wire", "both", "solid"):
        display.set_mode(scene, mode)
        assert solid_snapshot(scene) == before
        assert all(g.mesh is mesh for g, mesh in zip(bars, meshes))
        assert all(scene.entity_selectable(g) == (mode != "wire") for g in bars)
        actual = Counter(obj["class"] for obj in bim.collect_objects(scene))
        assert actual == expected
        assert actual["IfcReinforcingBar"] == 181
        wires = [g for g in scene.groups if display._wire_group(g)]
        assert len(wires) == 4
        assert all(not g.ifc and not g.mesh.faces for g in wires)


def test_shared_ties_and_wire_refresh_follow_move_undo_redo(specimen_scene):
    scene = specimen_scene
    display = plugin_module("dual_display")
    ties = [g for g in scene.groups if g.name.startswith("QA_SB-Tie-")]
    assert len(ties) == 29
    assert len({id(g.mesh) for g in ties}) == 1
    assert len({g.ext[display.GROUP_KEY]["definition"] for g in ties}) == 1
    group = ties[0]
    original_x = group.xform.map(QVector3D()).x()
    source_mesh = group.mesh
    metadata = deepcopy(group.ext)
    definitions = deepcopy(scene.plugin_data)
    wires = {g.uid for g in scene.groups if display._wire_group(g)}
    history = History(scene)

    def refreshed_x():
        stats = display.refresh_wire_overlays(scene)
        assert stats["bars"] == 181
        assert {g.uid for g in scene.groups if display._wire_group(g)} == wires
        wire = next(g for g in scene.groups if display._wire_group(g)
                    and g.ext[display.GROUP_KEY]["assembly_id"] == "QA_SB")
        return max(v.position.x() for v in wire.mesh.vertices)

    initial_max = refreshed_x()
    history.execute(MoveGroupCommand(group, QVector3D(100, 0, 0)))
    assert history.last_error is None
    assert refreshed_x() > 99
    assert history.undo()
    # QMatrix4x4 stores float32: a 100 m round trip can lose a few micrometres.
    assert group.xform.map(QVector3D()).x() == pytest.approx(original_x, abs=1e-5)
    assert refreshed_x() == pytest.approx(initial_max)
    assert history.redo()
    assert refreshed_x() > 99
    assert group.mesh is source_mesh
    assert group.ext == metadata
    assert scene.plugin_data == definitions
    assert all(g.mesh is source_mesh for g in ties)
