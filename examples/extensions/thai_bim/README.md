# Thai BIM Toolkit 0.5.0

An optional Thai-language extension for IngeTrazo Extension API 2. It adds an
11-button toolbar and illustrated, modeless dialogs for concrete members,
roof framing, straight concrete stairs, reinforcement and quantity takeoff.
It runs locally without an AI service or API key.

[ภาษาไทย / detailed Thai guide](README-th.md) ·
[Download the extension](https://github.com/buildsmart888/ingetrazo/releases/tag/thai-bim-v0.5.0)

## Install

1. Download `Thai-BIM-Toolkit-0.5.0.zip` from the release and extract it.
2. Copy the complete `thai_bim` folder into IngeTrazo's **user plugins folder**.
   On Windows this is `%APPDATA%\ingetrazo\plugins\thai_bim`.
   Alternatively, copy this directory from the repository and name it `thai_bim`.
3. Restart IngeTrazo. Open **Extensions → Thai BIM Toolkit…** or use the new toolbar.

Keep `__init__.py`, `engine.py`, `visuals.py`, `structures.py`, `builders.py` and `detailing.py`
together. PySide6 and NumPy are provided by the host application. The plugin
does not require `openpyxl`; that library is used only by the tests.

The native runtime checks were performed on Windows. Linux and macOS have not
been runtime verified. See the host's [plugin documentation](../../../docs/plugins.md)
for discovery and platform-specific plugin locations. The 0.x host API may change.

## Tools

| Tool | Behavior |
| --- | --- |
| Project | Grid X/Y and named levels, stored with the document |
| Footing, column, beam, slab | Editable RC presets, illustrated dimensions, Grid/Level placement, selected-member updates |
| Roof | Gable, hip/pyramid and shed; roof covers, C-section rafters, battens and shared ridge/hip members |
| Multi-plane roof | Read actual `IfcRoof` faces, preview clipped rafters/battens, inspect cross-sections and advanced JSON |
| Stair | Straight RC flight with user-set riser count, going and waist thickness; selected-flight updates |
| Reinforcement | Footing/slab meshes, column/beam cages and straight-stair bottom meshes, associated with the selected Thai BIM concrete host |
| BBS | Per-host shape marks, exact cut lengths, counts, nominal masses, selected-row shape preview and three-sheet Excel export |
| QTO | Excel/CSV with measurement basis and issues; invalidates reinforcement quantities when its host is changed/missing |
| Stock cutting | Material-separated stock plans with net lengths, lap allowances, kerf and reusable offcuts |

Toolbar buttons have tooltips and the toolbar can be moved or floated. Preview
changes do not build geometry: use the explicit create/update action. Creating
a new roof/stair makes an independent assembly; updating requires one selected
member of that assembly. Rebuilding reinforcement on the same host updates the
existing set. Updates retain matching slot IDs, reconcile removed pieces, and
support Undo. Manually edited/transformed assemblies and hosts are blocked.

![Hip-roof assembly preview](docs/images/hip-roof-dialog.png)

![Footing U hooks with real curved bends](docs/images/footing-detail-dialog.png)

![BBS with individual shape preview](docs/images/bbs-dialog.png)

## Modeling limits

These tools model **user-specified dimensions**, not structural strength designs.
Default dimensions are editable examples, not engineered sizes.

- Footing L/U hooks, curved ties with two 135-degree tails, centre splices and straight anchorage extensions use explicit user input. Bend radius is measured at the inside face. These internal shape names are not standard shape codes or certified structural designs.
- BBS includes analytic arc lengths and nominal circular diameter mass at user-supplied density. Legacy, edited/transformed bars, and bars with changed/missing hosts are excluded. Slab and stair bars retain the earlier geometry and do not enter the detailed BBS.
- Main laps are modeled as two parallel bars offset inward by 1.5 diameters. Nearby parallel main-bar collisions are rejected; whole-model clashes and adjacent concrete embedment are not checked.
- Concrete quantities are gross solids; intersections are not deducted.
- The stair tool currently supports straight flights, without landings or rails.
  The waist extends below the lower-floor datum at the start; support interfaces
  must be detailed separately.
- Roof sections are user presets. Connections, strength checks, tile-gauge
  verification, tile overlaps and accessories are not included.
- Concrete edits require explicit reinforcement regeneration. Rotated/transformed
  or manually edited hosts are not supported by the reinforcement generator.
- PDF/OCR, architecture/MEP generators, construction sheets and LOD 350
  certification are outside this release.

See the Thai guide for axis conventions, cover definitions and all restrictions.
The example `.igz`, `.glb` and `.xlsx` files in [examples](examples/) were generated
in isolated test scenes; they are modeling examples, not construction designs.

## Verification

The original installed implementation passed **22 pure engine tests** and
**34 native checks** for solids, toolbar/dialog actions, stable updates, Undo,
host association, QTO invalidation, IGZ persistence and GLB export. Native checks
left the user's document geometry unchanged. Evidence is in
[RELEASE.json](RELEASE.json) and [evidence/live-checks.json](evidence/live-checks.json).

Run the portable tests from the repository root:

```sh
python -m pip install -r examples/extensions/thai_bim/tests/requirements.txt
python -m unittest discover -s examples/extensions/thai_bim/tests -p "test_*.py"
```

Current detailed reinforcement examples are `examples/detailed-rebar-test.igz`, `examples/detailed-rebar-test.glb` and `examples/detailed-BBS.xlsx`. Older stair examples remain unchanged.

The native test script requires the plugin to be installed and enabled. Run it
in IngeTrazo's Python Console/AI bridge, where `scene` and `viewport` are supplied:

```python
import runpy
from core.extensions import user_plugins_dir
runpy.run_path(
    str(user_plugins_dir() / 'thai_bim' / 'tests' / 'live_thai_bim_v05.py'),
    init_globals={'scene': scene, 'viewport': viewport},
)
```

Native tests temporarily open dialogs and write results into `verification-local/`
inside the installed plugin. They operate model-generation checks in isolated
scenes and verify that the active document remains unchanged.

## License and references

GPL-3.0-or-later; see [LICENSE](LICENSE). Icons and illustrations are drawn in Qt
by this extension. No third-party logos or API credentials are bundled.
The dialog/toolbar patterns were studied from IngeTrazo's Windowizer example
and the public [Stair Maker / Kitchen Maker examples](https://github.com/aashishzharbade-arch/ingetrazo-extensions).
