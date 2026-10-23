"""Create repeated-storey RC stress fixtures, not engineered building designs."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def repeat_storeys(source, storeys, modules_per_storey):
    from core.group import Group
    from core.scene import Scene
    from PySide6.QtGui import QMatrix4x4

    if storeys < 1 or modules_per_storey < 1:
        raise ValueError("Storeys and modules per storey must be positive")
    scene = Scene()
    scene.layers = deepcopy(source.layers)
    scene.plugin_data = deepcopy(source.plugin_data)
    sources = [g for g in source.groups if g.mesh.faces or g.mesh.edges]
    for level in range(storeys):
        for module in range(modules_per_storey):
            prefix = f"L{level + 1:02d}-M{module + 1:02d}-"
            offset = QMatrix4x4()
            offset.translate(float((module % 3) * 18), float((module // 3) * 10), level * 3.6)
            for original in sources:
                if original.children:
                    raise ValueError("Scale fixture expects the flat native specimen layout")
                group = Group(original.mesh, name=prefix + original.name)
                group.xform = offset * original.xform if original.xform is not None else offset
                group.layer, group.component = original.layer, original.component
                group.hidden, group.locked = original.hidden, original.locked
                group.material = deepcopy(original.material)
                group.ifc = deepcopy(original.ifc)
                if group.ifc:
                    group.ifc.update(name=group.name, id=group.uid)
                # Signed centreline definitions remain immutable/shared; each
                # placement owns its mutable provenance and arrangement data.
                group.ext = {key: value if key == "go_rebar" else deepcopy(value)
                             for key, value in (original.ext or {}).items()}
                for key, field in (("go_rc_beam", "beam_id"),
                                   ("go_rc_column", "column_id")):
                    block = group.ext.get(key)
                    if block and field in block:
                        block[field] = prefix + block[field]
                for key in ("go_rc_native_bim", "go_rc_dual_display"):
                    block = group.ext.get(key)
                    if block and "assembly_id" in block:
                        block["assembly_id"] = prefix + block["assembly_id"]
                    if block and "original_parent" in block:
                        block["original_parent"] = prefix + block["original_parent"]
                group.ext["go_rc_scale"] = {
                    "storey": level + 1, "module": module + 1,
                    "source_uid": original.uid, "source_name": original.name,
                }
                scene.groups.append(group)
    scene.plugin_data["go_rc_scale"] = {
        "version": 1, "storeys": storeys, "modules_per_storey": modules_per_storey,
        "storey_height_m": 3.6,
        "scope": "repeated independent specimens; no structural/joint/slab design",
    }
    scene.version += 1
    return scene


def describe(scene):
    bars = [g for g in scene.groups if (g.ifc or {}).get("class") == "IfcReinforcingBar"]
    return {
        "groups": len(scene.groups), "bars": len(bars),
        "bar_prototypes": len({id(g.mesh) for g in bars}),
        "unique_meshes": len({id(g.mesh) for g in scene.groups}),
        "placed_faces": sum(len(g.mesh.faces) for g in scene.groups),
        "placed_edges": sum(len(g.mesh.edges) for g in scene.groups),
        "bars_per_storey": dict(Counter(g.ext["go_rc_scale"]["storey"] for g in bars)),
        "mass_kg": sum((g.ext.get("go_rc_beam") or g.ext.get("go_rc_column"))["weight_kg"]
                       for g in bars),
        "unique_uids": len({g.uid for g in scene.groups}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from core.scene import Scene
    from formats.igz import load_into, save_scene

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Scene()
    load_into(source, args.source.resolve(strict=True))
    reports = []
    for levels, modules in ((3, 2), (10, 6)):
        scene = repeat_storeys(source, levels, modules)
        row = describe(scene)
        path = output / f"rc-{row['bars']}-bars-{levels}-storeys.igz"
        save_scene(scene, path)
        # Verify compact native persistence without baking every placement.
        loaded = Scene()
        load_into(loaded, path)
        row["persistence_counts_and_mass"] = describe(loaded) == describe(scene)
        row.update(file=path.name, storeys=levels, modules_per_storey=modules)
        reports.append(row)
        print(json.dumps(row), flush=True)
        del loaded, scene
    (output / "scale-models.json").write_text(
        json.dumps(reports, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if all(row["persistence_counts_and_mass"] for row in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
