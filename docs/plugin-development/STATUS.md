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
- Four-specimen replay: `scripts/rc_specimens.py`, with editable `.igz` and
  column BBS outputs. Native synthetic selection replay:
  `scripts/rc_native_selection.py`. See [measured evidence](RC_V0103_BASELINE.md).

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
- PASS in this increment: 29 targeted tests in 36.34 seconds, including
  seven real-specimen dimension/persistence/display/Undo checks.
- PASS: standalone specimen replay and isolated native OpenGL selection replay,
  both exit 0; 181 real bars selected, zero extra BIM collection calls.
- NOT TESTED: interactive launcher acceptance, fresh installed-host v0.10.3
  replay, physical mouse interaction, whole-building scalability.

## Next work

Profile remaining first-use Solid selection stalls (~0.43-0.49 s) in picking,
selection overlays, Properties/solid checks and GPU work. Inherited BIM cache
reuse now has representative native evidence. Preserve native IDs/BBS and
the frozen deployed source until a measured fix is ready. Do not compare
timings directly with the older packaged v0.10.1 fixture as a speedup claim.

```powershell
# From the parent folder of the plugin development checkout:
cd .\ingetrazo-plugin-development
$env:PYTHONUTF8='1'
.venv-plugins\Scripts\python.exe -m pytest extensions/go-rc-detailing/tests tests/test_rc_plugin_launcher.py -q
.venv-plugins\Scripts\python.exe scripts/start_rc_plugin_dev.py
.venv-plugins\Scripts\python.exe scripts/rc_specimens.py --output ../rc-specimens-new
.venv-plugins\Scripts\python.exe scripts/rc_native_selection.py ../rc-specimens-new/four-rc-specimens.igz --output ../rc-native-new
```

Deferred GO Structural Analysis tasks remain deferred. Keep source-host tests,
installed application behavior and engineering validation as separate evidence.
