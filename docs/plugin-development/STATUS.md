# Plugin development status - 2026-10-24

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

Scale fixtures now contain 1,086 and 10,860 bars with successful native
save/load. Host box selection and leaf-instance selection outlines avoid
unnecessary placed geometry; 86 targeted tests passed, one OpenSKP-dependent
export test deselected. See [scale work and resume commands](RC_SCALE_SELECTION.md).

NEXT: rerun isolated native click/box/orbit/zoom after freeing machine memory.
The old 1,086-bar run hit a memory-floor stop during window selection; post-fix
large runs were refused at startup because only 161-177 MB was available.
Native performance improvement and large-model navigation remain NOT TESTED.
Keep the installed application unchanged until source-host acceptance passes.

Latest requested 10-storey trial: actual launch stopped at
`model_open_and_first_frame` after 30.156 s by the 1,400 MB private-memory
guard (observed 1,403.96 MB private / 834.50 MB RSS; machine available 16.38 MB).
Open acceptance NOT PASSED; selecting/box/orbit/zoom NOT TESTED in this run.
No test worker remained. See the scale report for the limits and next attempt.

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
