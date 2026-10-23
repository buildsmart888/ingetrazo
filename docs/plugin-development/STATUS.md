# Plugin development status - 2026-10-23

## Completed

- Development worktree: `ingetrazo-plugin-development`, branch
  `codex/plugin-development`.
- Host base: IngeTrazo 0.5.9, with existing integration selection caches and
  rebar LOD. Previous main is retained through merge `16c5294e` and remote
  `archive/main-before-v059-20261023`.
- GO RC Detailing deployed v0.10.3 imported in `8ab9d1a3`; 47 Python files
  match their captured hashes. Accepted beam v0.7 remains byte-for-byte locked.
- Disposable source-host launcher: `scripts/start_rc_plugin_dev.py`.

## Validation

- PASS: 62 focused host tests for BIM/picking/bounds caches, extension API and
  rebar LOD; 38.51 seconds, CPython 3.12.14 / PySide6 6.11.2, offscreen Qt.
- PASS: 2 RC migration tests; launcher staging/isolation test also passed.
- PASS: launcher syntax compilation.
- PASS: final combined acceptance run, 65 passed in 36.79 seconds (focused
  host tests, RC migration checks and disposable launcher staging).
- Initial broad host run stopped after a Windows cp874 decoding failure in an
  AUTHORS-file test. That test passes with `PYTHONUTF8=1`. The broad UTF-8
  rerun was stopped around 9% to keep this import's acceptance scoped to the
  affected host/plugin boundaries; it is INCOMPLETE, not a full-suite pass.
- NOT TESTED: interactive launcher acceptance, fresh installed-host v0.10.3
  specimen replay, mouse-selection timings, whole-building scalability.

## Next work

Recreate four disposable specimens using this source-host and v0.10.3 package,
then compare first/repeated click and box selection against historical v0.10.1
evidence. Verify native bar IDs, BBS/centrelines and save/load before changing
performance code. Inspect inherited cache behavior first.

```powershell
# From the parent folder of the plugin development checkout:
cd .\ingetrazo-plugin-development
$env:PYTHONUTF8='1'
.venv-plugins\Scripts\python.exe -m pytest extensions/go-rc-detailing/tests tests/test_rc_plugin_launcher.py -q
.venv-plugins\Scripts\python.exe scripts/start_rc_plugin_dev.py
```

Deferred GO Structural Analysis tasks remain deferred. Keep source-host tests,
installed application behavior and engineering validation as separate evidence.
