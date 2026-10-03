# Thai BIM Toolkit 0.7.0

An optional Thai-language extension for IngeTrazo Extension API 2. It adds an
15-button toolbar and illustrated, modeless dialogs for concrete members,
roof framing, straight concrete stairs, reinforcement and quantity takeoff.
It runs locally without an AI service or API key.

[ภาษาไทย / detailed Thai guide](README-th.md) ·
[Download the extension](https://github.com/buildsmart888/ingetrazo/releases/tag/thai-bim-v0.7.0)

## Install

1. Download `Thai-BIM-Toolkit-0.7.0.zip` from the release and extract it.
2. Copy the complete `thai_bim` folder into IngeTrazo's **user plugins folder**.
   On Windows this is `%APPDATA%\ingetrazo\plugins\thai_bim`.
   Alternatively, copy this directory from the repository and name it `thai_bim`.
3. Restart IngeTrazo. Open **Extensions → Thai BIM Toolkit…** or use the new toolbar.

Keep `__init__.py`, `engine.py`, `visuals.py`, `structures.py`, `builders.py`, `detailing.py`, `placement.py` `workflow.py`, `steel.py` and `management.py`
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
| Click placement | Centre/corner anchors, Grid/Level, Z rotation, repeated native viewport placement with one Undo per click |
| Host review | Detect changed hosts, preview before/after bars, require renewed review after changes, preserve IDs during regeneration |
| BBS | Per-host shape marks, exact cut lengths, counts, nominal masses, selected-row shape preview and three-sheet Excel export |
| QTO | Excel/CSV with measurement basis and issues; invalidates reinforcement quantities when its host is changed/missing |
| Stock cutting | Material-separated stock plans with net lengths, lap allowances, kerf and reusable offcuts |

Toolbar buttons have tooltips and the toolbar can be moved or floated. Preview
changes do not build geometry: use the explicit create/update action. Creating
a new roof/stair makes an independent assembly; updating requires one selected
member of that assembly. Rebuilding reinforcement on the same host updates the
existing set. Updates retain matching slot IDs, reconcile removed pieces, and
support Undo. Manually edited hosts and non-rigid transforms are blocked. Reinforcement follows rigid host translations/rotations after explicit review and regeneration.

![Hip-roof assembly preview](docs/images/hip-roof-dialog.png)

![Grid/Level and rotated RC placement](docs/images/placement-dialog.png)

![Explicit reinforcement review after host changes](docs/images/host-rebar-review.png)

![BBS with individual shape preview](docs/images/bbs-dialog.png)

## Modeling limits

These tools model **user-specified dimensions**, not structural strength designs.
Default dimensions are editable examples, not engineered sizes.

- Footing L/U hooks, curved ties with two 135-degree tails, centre splices and straight anchorage extensions use explicit user input. Bend radius is measured at the inside face. These internal shape names are not standard shape codes or certified structural designs.
- BBS includes analytic arc lengths and nominal circular diameter mass at user-supplied density. Legacy, edited or independently transformed bars, and bars with changed/missing hosts are excluded. Slab and stair bars retain the earlier geometry and do not enter the detailed BBS.
- Main laps are modeled as two parallel bars offset inward by 1.5 diameters. Nearby parallel main-bar collisions are rejected; whole-model clashes and adjacent concrete embedment are not checked.
- Concrete quantities are gross solids; intersections are not deducted.
- The stair tool currently supports straight flights, without landings or rails.
  The waist extends below the lower-floor datum at the start; support interfaces
  must be detailed separately.
- Roof sections are user presets. Connections, strength checks, tile-gauge
  verification, tile overlaps and accessories are not included.
- Concrete edits require explicit reinforcement review/regeneration. Rigid translation and rotation are supported; scale, shear, mirrors and manually edited host meshes remain blocked.
- New RC members use placement matrices so native Move/Rotate keeps their parametric meshes intact. Adopt old untouched members through the placement dialog before moving; old baked moves require host reconstruction.
- Placement UI supports upright members and Z rotation. Reinforcement review also accepts rigid tilted hosts. Placement always locks Z to the chosen base level, even when snapping named geometry points.
- Host notices inspect host geometry and bar poses. Individual bar-face edits are checked during review, regeneration, QTO and BBS.
- PDF/OCR, architecture/MEP generators, construction sheets and LOD 350
  certification are outside this release.

See the Thai guide for axis conventions, cover definitions and all restrictions.
The example `.igz`, `.glb` and `.xlsx` files in [examples](examples/) were generated
in isolated test scenes; they are modeling examples, not construction designs.

## Verification

The original installed implementation passed **32 pure engine tests** and
**58 native checks** for solids, toolbar/dialog actions, stable updates, Undo,
host association, QTO invalidation, IGZ persistence and GLB export. Native checks
left the user's document geometry unchanged. Evidence is in
[RELEASE.json](RELEASE.json) and [evidence/live-checks.json](evidence/live-checks.json).

Run the portable tests from the repository root:

```sh
python -m pip install -r examples/extensions/thai_bim/tests/requirements.txt
python -m unittest discover -s examples/extensions/thai_bim/tests -p "test_*.py"
```

Current placement/review examples are `examples/placed-host-rebar.igz`, `examples/placed-host-rebar.glb` and `examples/placed-host-BBS.xlsx`. Older detailing/stair examples remain unchanged. Native test scripts for v0.4/v0.5 are historical and require their corresponding released plugin.

The native test script requires the plugin to be installed and enabled. Run it
in IngeTrazo's Python Console/AI bridge, where `scene` and `viewport` are supplied:

```python
import runpy
from core.extensions import user_plugins_dir
runpy.run_path(
    str(user_plugins_dir() / 'thai_bim' / 'tests' / 'live_thai_bim_v06.py'),
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


## 0.7: layers and lighter reinforcement

New members use kind-specific structural layers; bars use host-kind layers.
The Layer / lightweight-model dialog migrates existing Thai BIM tags without replacing geometry, toggles visibility, converts one selected host cage, and saves a compressed native IGZ copy. Creation preserves existing members; selected updates cannot silently change kind. Stale prepared scene snapshots are rejected before replacing geometry.

New cages default to Lightweight (6-sided sections / 30-degree arc sampling).
Full uses 12 sides / 10-degree arcs. Centreline uses edges without solid faces;
use Full/Lightweight for surface-only exporters or renderers. All modes retain
analytic detailed cut lengths, masses and stable bar identities. Hiding bar layers
helps navigation; QTO/BBS still counts trusted hidden bars. Compression reduces
disk size, while display mode reduces mesh complexity in memory.

Independent main/tie selectors include TIS20-2559 RB/SR24, TIS24-2559 DB/SD30/40/50,
and ASTM A615/A615M numbered bars #3–#11, #14 and #18 in separate SI/inch sets.
Nominal dimensions come from published tables, including #9–#18 exceptions.
DB ribs are metadata rather than modeled geometry. Grade is a user specification;
no material certificate or strength design is generated. A706 presets are not included.
Old unclassified bars retain Custom/unspecified unless the user chooses a catalogue.
BBS adds specified catalogue, size, surface and grade columns; mass remains nominal
circular diameter times input density, not a rounded standard-mass lookup.

Verified 29-bar comparison: Full 15,526 faces / 21,088,108 bytes native IGZ;
Lightweight 3,256 faces / 4,678,153 bytes; Centreline 0 faces / 827,391 bytes.
Compressed copies were 756,288 / 152,456 / 32,752 bytes respectively.
All reopened in the installed host with valid BBS. This is a synthetic fixture,
not a whole-house navigation/FPS benchmark. Floor/stair paths remain net-path
QTO and are excluded from detailed fabrication BBS.

![Rebar catalogues and display modes](docs/images/rebar-catalogue.png)
![Layers and light model controls](docs/images/layer-manager.png)

Sources: [TIS20](https://www.tisi.go.th/data/standard/fulltext/TIS-20-2559p.pdf),
[TIS24](https://www.tisi.go.th/data/standard/fulltext/TIS-24-2559p.pdf),
[NYSDOT dimensions](https://www.dot.ny.gov/divisions/engineering/technical-services/technical-services-repository/alme/pages/850-1b.html),
[CRSI nominal inch diameters](https://www.crsi.org/wp-content/uploads/CRSI_MSP_29th_Ed_Errata-Nov2019.pdf),
[ASTM scope](https://store.astm.org/a0615_a0615m-26.html).
See `evidence/performance-v07.json` and the current `RELEASE.json`.
