# GO RC Detailing development baseline

This package captures the deployed v0.10.3 Python source on 2026-10-23 for
development against IngeTrazo 0.5.9 / extension API 2. It is not a newly released
plugin. `baseline-manifest.json` records every imported Python file and the
accepted, locked beam baseline hash. Runtime caches are omitted.

The source package is `go_rc_detailing/`. No installed plugin or user document
was changed by this import. Use a disposable plugin directory and source-host
process when testing; do not copy into a user's AppData as a development step.

Run from the repository root with a matching PySide6 6.11.2 environment:

```powershell
python -m pytest extensions/go-rc-detailing/tests -q
```

To open an isolated source-host window manually:

```powershell
python scripts/start_rc_plugin_dev.py
```

The launcher stages the plugin in a temporary data directory and waits for its
own source-host process to close. Save any wanted test model outside that
temporary directory. The interactive launcher has not been acceptance-tested
as part of the source import.

The package tests establish source integrity, loader compatibility and the
locked beam boundary. Host integration tests in `tests/test_go_rc_specimens.py`
also build four real specimens and check dimensions, native IDs, BBS metadata,
shared tie meshes, save/load, display modes and move/Undo/Redo wire refresh.
These checks do not establish engineering design compliance or building scale.

## Reproduce the four-specimen baseline

From the repository root, using the matching development environment:

```powershell
$env:PYTHONUTF8='1'
python -m pytest tests/test_go_rc_specimens.py -q
python scripts/rc_specimens.py --output ../rc-specimens-new
python scripts/rc_native_selection.py ../rc-specimens-new/four-rc-specimens.igz --output ../rc-native-new
```

Both output directories must be new. The first command-line replay creates an
editable `.igz`, column BBS/BOQ output, a build log and a JSON acceptance report.
It exercises accepted beam geometry phases without beam IFC export. The native
replay opens its own Windows/OpenGL source window, discovers a temporary copy
of this plugin and drives synthetic click/window/crossing events. It records
the first and repeated clicks, frame/handler slices, box-release costs, selected
bar counts and BIM collection calls. Settings/data are isolated. Its parent
cleans the sandbox after the child releases the GPU driver's cache files.

Wire is an assembly-batched display: selection picks wire groups rather than
individual authoritative bars. Use Solid or Both for per-bar selection. Wire
groups have no IFC tag and contribute no reinforcement quantities.

See [v0.10.3 evidence](../../docs/plugin-development/RC_V0103_BASELINE.md) for
tested scope and limitations. The older packaged-host v0.10.1 diagnostic uses
different runtime/geometry and is not a controlled speedup comparison.

For 1,086/10,860-bar repeated-storey fixtures, the optional QA dependencies,
memory-bounded native replay and pending acceptance, see
[scale selection work](../../docs/plugin-development/RC_SCALE_SELECTION.md).

Future source edits must deliberately update the baseline provenance rather
than silently rewriting the accepted beam implementation. Display meshes and
wire overlays must preserve native bar identities and centreline/BBS authority.
