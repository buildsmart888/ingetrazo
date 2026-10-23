"""Scale fixtures preserve prototypes/provenance and guard only their workers."""
import json
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D

from core.group import Group
from core.mesh import Mesh
from core.scene import Scene
from formats.igz import save_scene, load_into
from scripts.rc_scale_models import repeat_storeys, describe
from scripts.rc_native_selection import guarded_run


def source():
    mesh = Mesh()
    mesh.add_face([QVector3D(), QVector3D(1, 0, 0), QVector3D(1, 1, 0)])
    group = Group(mesh, name="B1-Main")
    group.ifc = {"class": "IfcReinforcingBar", "name": group.name, "id": group.uid}
    group.xform = QMatrix4x4()
    group.ext = {
        "go_rc_beam": {"beam_id": "B1", "length_m": 1.0, "weight_kg": 2.0},
        "go_rc_native_bim": {"assembly_id": "B1", "original_parent": "B1-RC"},
        "go_rc_dual_display": {"assembly_id": "B1", "definition": "path-1"},
    }
    return Scene(groups=[group])


def test_scale_instances_are_shared_but_mutable_provenance_and_ids_are_independent(tmp_path):
    original = source()
    original_tag = dict(original.groups[0].ifc)
    scene = repeat_storeys(original, 10, 6)
    report = describe(scene)
    assert report["bars"] == report["unique_uids"] == 60
    assert report["bar_prototypes"] == 1
    assert report["mass_kg"] == 120.0
    assert report["bars_per_storey"] == {index: 6 for index in range(1, 11)}
    assert all(g.mesh is original.groups[0].mesh for g in scene.groups)
    assert len({g.ifc["id"] for g in scene.groups}) == 60
    assert len({g.ext["go_rc_native_bim"]["assembly_id"] for g in scene.groups}) == 60
    scene.groups[0].ext["go_rc_beam"]["weight_kg"] = 3.0
    assert scene.groups[1].ext["go_rc_beam"]["weight_kg"] == 2.0
    assert original.groups[0].ext["go_rc_beam"]["weight_kg"] == 2.0
    assert original.groups[0].ifc == original_tag
    assert scene.groups[-1].xform.map(QVector3D()).z() == pytest.approx(32.4, abs=1e-5)
    path = tmp_path / "scale.igz"
    save_scene(scene, path)
    loaded = Scene()
    load_into(loaded, path)
    assert describe(loaded) == describe(scene)
    assert [g.uid for g in loaded.groups] == [g.uid for g in scene.groups]


@pytest.mark.parametrize("levels,modules", [(0, 1), (1, 0), (-1, 6)])
def test_invalid_scale_is_rejected(levels, modules):
    with pytest.raises(ValueError):
        repeat_storeys(source(), levels, modules)


def test_guard_refuses_startup_when_machine_memory_is_already_low(monkeypatch, tmp_path):
    import psutil
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=100 * 1048576))
    import scripts.rc_native_selection as replay
    monkeypatch.setattr(replay.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start"))
    output = tmp_path / "low-memory"
    args = SimpleNamespace(min_free_mb=384)
    assert guarded_run([], {}, output, args) == 1
    report = json.loads((output / "resource-guard.json").read_text())
    assert report["status"] == "INSUFFICIENT_STARTUP_HEADROOM"
    assert report["worker_started"] is False


def test_memory_guard_stops_only_its_worker_tree(monkeypatch, tmp_path):
    import scripts.rc_native_selection as replay
    terminated = []

    class Worker:
        def __init__(self, pid):
            self.pid = pid

        def is_running(self):
            return self.pid not in terminated

        def children(self, recursive):
            return [child]

        def memory_info(self):
            return SimpleNamespace(rss=100 * 1048576, private=100 * 1048576)

        def terminate(self):
            terminated.append(self.pid)

    owner, child = Worker(1), Worker(2)
    process = SimpleNamespace(pid=1, poll=lambda: None, wait=lambda: 15)
    fake = SimpleNamespace(
        Process=lambda pid: owner if pid == 1 else pytest.fail("unowned PID"),
        virtual_memory=lambda: SimpleNamespace(available=2000 * 1048576),
        wait_procs=lambda workers, timeout: (workers, []), NoSuchProcess=ProcessLookupError,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)
    monkeypatch.setattr(replay.subprocess, "Popen", lambda *a, **k: process)
    output = tmp_path / "guarded"
    args = SimpleNamespace(min_free_mb=384, max_private_mb=150, timeout=180)
    assert guarded_run([], {}, output, args) == 1
    assert terminated == [2, 1]
    report = json.loads((output / "resource-guard.json").read_text())
    assert report["status"] == "PRIVATE_MEMORY_LIMIT"
    assert report["peak_worker_tree_private_mb"] == 200.0
