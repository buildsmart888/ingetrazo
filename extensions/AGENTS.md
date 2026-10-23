# GO plugin development instructions

- Read the plugin's README and task before editing. Keep code, comments and
  commit messages in English, following the repository CONTRIBUTING guide.
- Target the stated host/API boundary explicitly: the initial workspace is
  IngeTrazo 0.5.9 / extension API 2. Do not claim other versions are supported
  without evidence.
- Preserve native editable identities, shared mesh prototypes, transforms,
  IFC tags, engineering metadata and user-authored edits.
- Route document changes through undoable host commands with rollback. Keep
  display-only state outside analytical/quantity provenance.
- Keep accepted bar centrelines and BBS authority independent of display LOD.
  A lighter viewport must not silently change bar lengths or quantities.
- Diagnose host and plugin costs separately. Keep host fixes in focused commits
  under the host source tree; never patch an installed Program Files binary.
- Back up before migrating a baseline or installing. Prefer isolated plugin
  directories and disposable test documents; do not close or replace user work.
- Add tests appropriate to the change. For selection performance, assert both
  correct invalidation on geometry changes and reuse on selection-only changes.
- Record Passed, Failed and Not Tested honestly, including exact fixture size,
  host/runtime and measurement scope. Instrumented timings are not raw FPS.
- Do not duplicate existing extension source trees or mix deferred unrelated
  work into a plugin feature commit. Never publish credentials or project data.
