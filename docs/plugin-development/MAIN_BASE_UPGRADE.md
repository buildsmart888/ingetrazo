# Main base upgrade - 2026-10-23

The new base is IngeTrazo 0.5.9, upstream commit
`24e7ada6df9f0b4f5f761f287aaade9e40e6728c`, through the existing
`integration/go-v0.5.9-rebar-lod` integration. The plugin development branch
and main share the reviewed upgrade commit at publication.

Old main `2daee48d4760cb4b6cbc406d11e8fbf0b9c07d1d` is retained both as a merge
parent and remote branch `archive/main-before-v059-20261023`. No force push is
needed. The sole merge conflict, Thai BIM's extension entrypoint, keeps the
integration version: old main functionality plus optional centreline LOD tags.
The historical public GO Structural Analysis snapshot remains in the tree;
the independently maintained GO checkout remains authoritative.

GO RC Detailing is imported as a deployed v0.10.3 source snapshot. This does
not install a new packaged application or replace the user's AppData plugin.
The original dirty checkout is preserved. Continue plugin work in the separate
`ingetrazo-plugin-development` worktree on `codex/plugin-development`.

Validation uses CPython 3.12.14 / PySide6 6.11.2, with offscreen Qt for host
tests. Focused selection, BIM cache, extension API and rebar LOD tests: 62
passed. Final combined host/RC/launcher run: 65 passed in 36.79 seconds.
The broad host fast-suite UTF-8 rerun is
INCOMPLETE; see the publication status document. Installed-host mouse
interaction, v0.10.3 four-specimen replay and whole-building performance remain
NOT TESTED for this imported snapshot.
