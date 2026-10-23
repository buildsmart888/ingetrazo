# GO plugin development workspace

Branch: `codex/plugin-development` in `buildsmart888/ingetrazo`.
Base: `integration/go-v0.5.9-rebar-lod` at
`afc1490f55d7716a97923073f2f0b67f89c59a3c`, built on upstream IngeTrazo 0.5.9.
This is a development workspace, not an installed application release.

Use this directory for new GO plugin source packages and their own tests,
documentation and installers. Follow [the plugin API](../docs/plugins.md) and
[the development roadmap](../docs/plugin-development/ROADMAP.md).

## Source ownership

- GO RC Detailing is the first planned plugin package. Its installed v0.10.1
  baseline has been investigated, but its source has **not yet been imported
  into this branch**. Import a verified baseline with provenance and tests
  before editing it; do not treat a placeholder as an implemented plugin.
- Keep the existing Thai BIM source at `examples/extensions/thai_bim` as the
  single copy. The inherited isolated launcher already handles that package.
- GO Structural Analysis remains a separately maintained project. Integrate
  through a versioned data contract; do not copy an independently edited source
  tree over another checkout or publish private project data here.

Each plugin should keep a clear boundary between engineering data, native
document adapters and display/UI. Shared infrastructure should be extracted
only when multiple implemented plugins need it.

## Runtime and validation

Develop in an isolated source-host window and per-test plugin directory.
Existing launchers are documented in [README_REBAR_V059_TEST.txt](../README_REBAR_V059_TEST.txt).
Do not automatically install into the user's AppData or replace Program Files.
Inherited launchers and rebar LOD changes need their own acceptance checks;
creating this branch does not revalidate them.

Commit one scoped feature at a time. Keep automated, source-host, packaged-host
and physical interaction evidence separate. Work on the original main checkout
and deferred GO tasks remains independent of this branch.
