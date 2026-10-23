# GO RC Detailing v0.10.3 source-host baseline

Captured 2026-10-23 from the unmodified 47-file deployed snapshot. This
increment adds repeatable specimen/replay tools and integration tests; it
does not change plugin generation mathematics or introduce a performance fix.

## Specimens and persistence

| Specimen | Dimensions | Reinforcing bars | Ties / spiral |
| --- | --- | ---: | --- |
| Single beam | 4 m, 300 x 500 mm | 40 | 29 ties |
| Continuous beam | 4 / 3.5 / 4.5 m, 300 x 500 mm | 107 | 88 ties |
| Rectangular column | 300 x 400 mm, height 3 m | 25 | 21 ties |
| Circular column | diameter 400 mm, height 3 m | 9 | one 20-turn spiral |

The editable fixture contains 181 authoritative reinforcing bars, 20 unique
bar mesh prototypes, 204 native BIM rows and four untagged wire groups. With
an existing-object sentinel it has 215 top-level groups, 182,550 placed faces
and 381,750 placed edges. Wire adds display edges without adding IFC bars.

PASS: geometry extents, native bar UIDs, transforms, BBS lengths/masses,
prototype sharing and centreline definitions survive `.igz` save/open.
Solid/Wire/Both preserve authoritative solids. Moving a real tie and explicit
wire refresh follows its placement through Undo/Redo without changing BBS,
prototype meshes or wire group UIDs. These checks do not validate design-code
compliance, joint reinforcement, anchorage or IFC export. Beam replay runs
the accepted geometry/verification stages without its external IFC export.

## Selection evidence

Environment: Windows source host 0.5.9, CPython 3.12.14, PySide6 6.11.2,
AMD Radeon(TM) Graphics, OpenGL 3.3, vsync disabled. Native events are
synthetic Qt events handled by the real viewport, followed by event pumping
and GPU completion using the repository's interaction driver. Six full
clicks and one window/crossing drag were measured per display mode. Modes run
in Solid -> Wire -> Both order in one process, so later modes inherit warm
caches; this is not a controlled comparison of isolated cold modes.

| Mode | First full click (ms) | Repeated full click median (ms) | Window release (ms) | Crossing release (ms) |
| --- | ---: | ---: | ---: | ---: |
| Solid | 427.700 | 97.416 | 491.612 | 165.695 |
| Wire | 157.339 | 53.523 | 129.173 | 31.471 |
| Both | 205.319 | 82.570 | 125.183 | 116.479 |

These are single-run observations on this fixture, not performance budgets or
whole-building capacity. First click means the first click after opening and
settling the model, not a completely cold application start. Each full click
includes press and release; box costs above are the release phase only. Raw
phase summaries and event totals are preserved in
[native replay evidence](evidence/rc-v0103-native-selection.json).

PASS: both box directions select all 181 real bars in Solid/Both; Wire selects
batched assembly wires and other visible objects, not individual bars. All
native click/box runs caused **zero** additional `bim.collect_objects` calls.
The input `.igz` remained byte-identical. Plugin discovery succeeded and the
final child/parent process exited with code 0. Captured Solid/Wire screenshots
were visually inspected.

The separate offscreen CPU replay measured initial BIM collection at 813.399
ms; seven selection notifications took 0.014-3.634 ms with the original table
rows retained. This excludes viewport picking, painting and OpenGL. See
[source replay evidence](evidence/rc-v0103-source-replay.json).

## Validation and remaining work

- PASS: 29 targeted tests in 36.34 seconds: seven real-specimen checks plus
  BIM/picking/bounds cache, source integrity and launcher staging tests.
- PASS: standalone source replay and native replay, both exit 0.
- The initial native tool completed its interaction checks but failed sandbox
  cleanup because AMD held its GL cache open. The tool now cleans from the
  parent after worker exit; the final run above exited normally.
- Full host suite was not rerun for this increment. Earlier broad-suite
  status remains INCOMPLETE.
- NOT TESTED: packaged-host acceptance, physical mouse interaction, large
  multi-storey models or engineering design/IFC export validation.

The inherited host caches prevent the original document-wide BIM collection
on this representative selection workload. Stutter remains: Solid's first
click/window release is about 0.43-0.49 seconds and repeated clicks remain
around 97 ms on this machine. Next, isolate picking, selection overlays,
Properties/solid checks and first-use GPU work with this fixture before
changing code. Keep first-use and warmed results separate. Individual-bar
picking from the batched Wire view is a separate missing feature.

The older installed-host v0.10.1 timings used another runtime and fixture
layout; no speedup ratio or packaged-host fix is claimed from these results.
