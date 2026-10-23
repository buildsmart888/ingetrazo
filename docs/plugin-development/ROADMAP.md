# GO plugin development roadmap

Established 2026-10-23 on `codex/plugin-development`.
See [workspace ownership and setup](../../extensions/README.md).

## Current state

This branch inherits the v0.5.9 integration host and existing rebar LOD work.
The deployed RC v0.10.3 source snapshot is now imported with a 47-file hash
manifest and locked beam integrity checks. Old main history is retained in the
0.5.9 base. No new performance fix or design engine is introduced by this
import. Do not infer packaged-host performance from inherited branch history.

## P0: import and reproduce the RC baseline

1. DONE: capture deployed v0.10.3 Python source, preserving the locked accepted
   beam implementation. The original authoring repository is not established.
2. DONE on this branch: recreate the four native specimens: 4 m single beam; 4/3.5/4.5 m continuous
   beam; 300 x 400 mm rectangular column; 400 mm circular column, both 3 m high.
3. Source-host replay DONE, including native synthetic events and persistence;
   see [v0.10.3 evidence](RC_V0103_BASELINE.md). A controlled same-version
   installed/source comparison remains pending. The installed-host issue and
   inherited line-LOD/selection work are distinct.

Acceptance: native bar identities, dimensions, BBS and IFC metadata survive
save/load; existing documents and installations remain intact.

## P1: selection and BIM quantity invalidation

The packaged-host fixture reproduced a full BIM quantity refresh after
selection-only changes. See [the measured baseline](evidence/rc-selection-baseline.json).
`BimTray.on_scene_changed -> refresh -> collect_objects` dominated the measured
frame; world mesh construction and area/volume calculation were repeated.

- Separate selection/detail updates from full geometry/quantity invalidation.
- Cache quantities against appropriate geometry/mutation, transform and tag
  inputs. Do not key all expensive calculations on selection/view changes.
- Reuse shared prototype calculations where mathematically valid; preserve
  correct quantities for transformations, nested objects and class changes.
- Keep native groups, bar IDs and editable solids. Do not merge bars merely to
  hide the refresh cost.

Acceptance: selecting/clearing/box-selecting unchanged geometry does not trigger
full quantity calculation. Geometry edits, transforms, Undo/Redo, Open and tag
changes still invalidate correctly. Measure first and repeated interactions
separately. No numerical speedup target is claimed achieved yet.

Current evidence: the four-specimen native replay triggers zero additional
collections during clicks/window/crossing selection. Initial Solid selection
still has roughly 0.43-0.49 s stalls on the measured machine. Profile those
first-use paths next; do not duplicate the inherited quantity-cache fix.

## P2: large-model display and picking

Audit inherited LOD and placement/picking caches before adding another path.
Preserve full engineering data while using shared prototypes, batched drawing,
spatial filtering and display-only detail levels. Keep selection overlays
independent of geometry rebuilding. Support storey/member visibility filters.

Acceptance: identical bar identity, centreline/BBS and native persistence across
display modes; no stale picks after edits. Benchmark progressively larger
fixtures, then multi-storey assemblies, with time/memory evidence. A successful
four-specimen test does not establish whole-building capacity.

## P3: engineering model and GO Structural Analysis handoff

Define a versioned contract for source member IDs, units/axes, model and result
fingerprints, load case/combination provenance, design revision and reinforcement
ownership. Separate analysis demand, required reinforcement and arranged details.
Use Draft -> Preview -> Review -> Apply for generating or updating reinforcement,
including conflicts with manually edited details and stale-source rejection.

Start with one validated beam workflow before columns, slabs and stairs. Existing
area-load surfaces do not establish plate stiffness or slab reinforcement design.
Standards/version, applicability, anchorage/laps, cover/spacing, joints and other
detailing checks need explicit validated scope; geometry generation alone is not
capacity or code-compliance evidence.

## Release gates

- Plugin unit/regression checks and persistence tests.
- Isolated source-host tests with matching Qt/runtime.
- Fresh packaged-host startup and representative interaction checks.
- Quantity/design validation appropriate to each claimed engineering feature.
- Explicit handling of experimental features and untested model sizes.

This roadmap does not resume deferred FND-01 or other GO Structural Analysis work.
