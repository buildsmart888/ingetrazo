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

The tests establish source integrity, host loader compatibility and the locked
beam boundary. They do not establish interactive performance, whole-building
capacity, engineering design compliance or installed-host acceptance. The older
four-specimen diagnostic used v0.10.1; v0.10.3 needs a fresh native benchmark.

Future source edits must deliberately update the baseline provenance rather
than silently rewriting the accepted beam implementation. Display meshes and
wire overlays must preserve native bar identities and centreline/BBS authority.
