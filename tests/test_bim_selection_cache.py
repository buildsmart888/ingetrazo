# SPDX-License-Identifier: GPL-3.0-or-later
"""Selection must not remeasure repeated BIM geometry or rebuild its table."""
from __future__ import annotations

import re
from collections import Counter
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D

from core import bim
from core.group import Group
from core.history import History, ScaleGroupCommand
from core.mesh import Mesh
from core.scene import Scene
from formats.ifc import save_ifc
from views.tray import BimPanel, BimTray, EntityInfoPanel, Tray


def _box():
    mesh = Mesh()
    points = [QVector3D(*p) for p in (
        (0, 0, 0), (1, 0, 0), (1, 2, 0), (0, 2, 0),
        (0, 0, 3), (1, 0, 3), (1, 2, 3), (0, 2, 3))]
    for indices in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                    (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        mesh.add_face([points[i] for i in indices])
    return mesh


def _instances(count=3, ifc_class="IfcBeam"):
    scene, mesh = Scene(), _box()
    for i in range(count):
        group = Group(mesh, name=f"Element {i}")
        group.xform = QMatrix4x4()
        group.xform.translate(float(i * 10), 0.0, 0.0)
        group.ifc = {"class": ifc_class, "name": group.name}
        scene.groups.append(group)
    return scene


def _window(scene):
    viewport = SimpleNamespace(scene=scene, history=History(scene), update=lambda: None)
    return SimpleNamespace(viewport=viewport)


def test_translated_instances_measure_once_without_world_mesh_copies(monkeypatch):
    scene = _instances(100)
    calls = []
    volume = bim.face_set_volume

    def measured(faces):
        calls.append(1)
        return volume(faces)

    def no_copy(*_args, **_kwargs):
        pytest.fail("translated prototypes do not need copied world meshes")

    monkeypatch.setattr(bim, "face_set_volume", measured)
    monkeypatch.setattr("core.group.world_mesh", no_copy)
    monkeypatch.setattr("core.group.transformed_mesh", no_copy)
    objects = bim.collect_objects(scene)

    assert len(objects) == 100
    assert len(calls) == 1
    assert len({obj["key"] for obj in objects}) == 100
    assert sum(obj["volume"] for obj in objects) == pytest.approx(600.0)
    assert all(obj["area"] == pytest.approx(22.0) for obj in objects)
    assert all(obj["quantities"][2] == (6.0, "m3") for obj in objects)


def test_rotations_scales_and_tags_keep_correct_world_quantities():
    scene = _instances(4, "IfcPile")
    scene.groups[1].xform.rotate(90.0, 1.0, 0.0, 0.0)
    scene.groups[2].xform.scale(2.0, 3.0, 4.0)
    scene.groups[3].xform.scale(-2.0, 3.0, 4.0)
    objects = bim.collect_objects(scene)
    assert [obj["quantities"][2][0] for obj in objects] == pytest.approx([3, 2, 12, 12])
    assert [obj["volume"] for obj in objects] == pytest.approx([6, 6, 144, 144])

    # A new collection sees direct edits too; its cache cannot outlive this call.
    scene.groups[0].ifc = {"class": "IfcBeam", "name": "Retagged"}
    scene.groups[0].xform.scale(2.0)
    obj = bim.collect_objects(scene)[0]
    assert obj["name"] == "Retagged"
    assert obj["quantities"][2] == (48.0, "m3")
    assert ",48.0000,m3," in bim.quantities_csv(scene)


def test_nested_groups_measure_the_complete_placed_object():
    scene = _instances(2)
    a, b = scene.groups
    b.xform.setToIdentity()
    b.xform.translate(5.0, 0.0, 0.0)
    parent = Group(name="Assembly")
    parent.adopt([a, b])
    parent.xform.translate(20.0, 0.0, 0.0)
    parent.ifc = {"class": "IfcBeam", "name": "Assembly"}
    scene.groups = [parent]
    (obj,) = bim.collect_objects(scene)
    assert obj["volume"] == pytest.approx(12.0)
    assert obj["area"] == pytest.approx(44.0)
    values = {name: value for _kind, name, value in obj["quantities"][1]}
    assert values["Length"] == pytest.approx(6.0)
    assert bim.QuantityCache().solid_volume(parent) is None


def test_selection_changes_only_the_highlighted_bim_row(monkeypatch):
    scene = _instances()
    calls = []
    collect = bim.collect_objects

    def collected(scene):
        calls.append(1)
        return collect(scene)

    monkeypatch.setattr(bim, "collect_objects", collected)
    panel = BimPanel(_window(scene))
    dock = SimpleNamespace(bim=panel)
    rows = [panel.tree.topLevelItem(i) for i in range(3)]
    try:
        for group in (scene.groups[0], scene.groups[2], scene.groups[0]):
            scene.select([group])
            BimTray.on_scene_changed(dock)
            assert panel.tree.selectedItems() == [rows[scene.groups.index(group)]]
            assert all(panel.tree.topLevelItem(i) is rows[i] for i in range(3))
        scene.clear_selection()
        BimTray.on_scene_changed(dock)
        assert panel.tree.selectedItems() == []
        assert len(calls) == 1
    finally:
        panel.deleteLater()


def test_bim_refreshes_after_edits_undo_clear_and_document_replacement():
    scene = _instances(1)
    window = _window(scene)
    panel = BimPanel(window)
    try:
        assert panel.tree.topLevelItem(0).text(3) == "6.00"
        group = scene.groups[0]
        window.viewport.history.execute(ScaleGroupCommand(group, QVector3D(0, 0, 0), 2.0))
        panel.refresh(force=False)
        assert panel.tree.topLevelItem(0).text(3) == "48.00"
        assert window.viewport.history.undo()
        panel.refresh(force=False)
        assert panel.tree.topLevelItem(0).text(3) == "6.00"

        group.ifc["name"] = "Updated name"
        scene.version += 1
        panel.refresh(force=False)
        assert panel.tree.topLevelItem(0).text(1) == "Updated name"
        scene.clear()
        panel.refresh(force=False)
        assert panel.tree.topLevelItemCount() == 0

        replacement = _instances(2)
        replacement.version = scene.version
        replacement.view_version = scene.view_version
        window.viewport.scene = replacement
        panel.refresh(force=False)
        assert panel.tree.topLevelItemCount() == 2
    finally:
        panel.deleteLater()


def test_explicit_refresh_honours_direct_metadata_edits():
    scene = _instances(1)
    panel = BimPanel(_window(scene))
    try:
        scene.groups[0].ifc["name"] = "Direct edit"
        panel.refresh()
        assert panel.tree.topLevelItem(0).text(1) == "Direct edit"
    finally:
        panel.deleteLater()


def test_entity_info_reuses_solid_check_across_selected_instances(monkeypatch):
    from core import solids

    scene = _instances(3)
    calls = []
    report = solids.solid_report

    def checked(mesh):
        calls.append(1)
        return report(mesh)

    monkeypatch.setattr(solids, "solid_report", checked)
    panel = EntityInfoPanel(_window(scene))
    try:
        for group in scene.groups:
            scene.select([group])
            panel.refresh()
            assert "6.000" in panel._label.text()
        assert len(calls) == 1
        scene.groups[0].xform.scale(2.0)
        scene.version += 1
        scene.select([scene.groups[0]])
        panel.refresh()
        assert "48.000" in panel._label.text()
        assert len(calls) == 2
    finally:
        panel.deleteLater()


def test_selection_does_not_schedule_document_wide_tray_scans():
    scene = _instances(2)
    calls = Counter()

    def panel(name):
        def refresh():
            calls[name] += 1
        return SimpleNamespace(refresh=refresh, refresh_in_model=refresh)

    def schedule(_delay):
        calls["materials"] += 1

    tray = SimpleNamespace(
        _window=_window(scene), _mat_refresh_timer=SimpleNamespace(start=schedule),
        entity_info=panel("entity"), parts=panel("parts"), layers=panel("layers"),
        scenes=panel("scenes"), components=panel("components"))
    Tray.on_scene_changed(tray)
    scene.select([scene.groups[0]])
    Tray.on_scene_changed(tray)
    assert calls == Counter(entity=2, parts=2, layers=1, scenes=1, components=1, materials=1)
    scene.layers[0].locked = True
    scene.version += 1
    Tray.on_scene_changed(tray)
    assert calls == Counter(entity=3, parts=3, layers=2, scenes=2, components=2, materials=2)


def test_ifc_exports_each_instance_at_its_position_with_scaled_quantities(tmp_path):
    scene = _instances(2)
    scene.groups[0].xform.translate(10.0, 0.0, 0.0)
    scene.groups[1].xform.translate(10.0, 0.0, 0.0)
    scene.groups[1].xform.scale(2.0, 1.0, 1.0)
    path = tmp_path / "instances.ifc"
    assert save_ifc(scene, path) == 2
    text = path.read_text()
    points = {tuple(float(c) for c in coords.split(","))
              for coords in re.findall(r"IFCCARTESIANPOINT\(\(([^)]+)\)\)", text)}
    assert {(10.0, 0.0, 0.0), (11.0, 2.0, 3.0),
            (20.0, 0.0, 0.0), (22.0, 2.0, 3.0)} <= points
    assert (1.0, 2.0, 3.0) not in points
    guids = re.findall(r"IFCBEAM\('([^']+)'", text)
    assert len(guids) == len(set(guids)) == 2
    volumes = [float(v) for v in re.findall(
        r"IFCQUANTITYVOLUME\('GrossVolume',\$,\$,([\d.]+),", text)]
    assert volumes == pytest.approx([6.0, 12.0])
