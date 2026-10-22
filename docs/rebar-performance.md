# Rebar interaction performance

The rebar changes address duplicate geometry, repeated quantity calculations
on selection, and the amount of geometry drawn during interaction. The
[interactive display guide](rebar-display.md) describes the centreline renderer
and its fallback rules. The [RB9 demo guide](../scripts/GO_RB9_Stirrup_Fix.md)
describes the model and its parameters.

## Use the updated host and demo

1. Start IngeTrazo from a checkout containing these host changes. Restart an
   already-running application after updating its source.
2. Open a new document, then choose **Extensions → Python Console → Run script
   file…** and select `scripts/GO_RB9_Stirrup_Fix.py`.
3. Orbit, pan, zoom, or preview moving a bar. Compatible bars use their cached
   centrelines during interaction and return to solids afterward.

The console supplies one undo step. Rerunning the script replaces only its
`GO_RB9FIX_` objects. Existing bars with no verified centreline metadata remain
valid solids; rerun the updated producer to attach compatible metadata. The
generator can run in an older host, but that host does not gain the new
renderer or BIM cache from the script alone.

## Stored mesh versus placed triangles

The complete demo contains one beam, five longitudinal bars and nineteen RB9
stirrups. Every stirrup references one local mesh; each has its own placement
matrix, UID, name and BIM tag. The longitudinal bars share one mesh per colour.
The live instances also share an immutable centreline metadata block per
definition, avoiding repeated path packing during the first interaction.

| Complete beam demo | Value |
| --- | ---: |
| Objects | 25 |
| Unique meshes | 4 |
| Triangle faces stored in those meshes | 2,316 |
| Triangles represented by all placements at full detail, before culling | 41,676 |

One stirrup definition has 2,176 triangle faces and a 67-segment centreline.
Ten thousand instances still store one such mesh, but full-detail rendering
represents 21,760,000 placed triangles before culling. Sharing geometry does
not remove the work of drawing every visible placement. Centreline LOD is a
separate display optimization; picking, quantities and exports retain the
solid geometry.

## Reproduce the CPU benchmark

From the repository root, with the application's Python dependencies installed:

```bash
python benchmarks/rebar_interaction.py \
  --counts 100 1000 10000 \
  --repeats 3 \
  --selection-samples 50 \
  --baseline-ref 2daee48d4760cb4b6cbc406d11e8fbf0b9c07d1d \
  --output /tmp/rebar-interaction-results.json
```

Use an appropriate output path on Windows. The baseline commit must be
available in the local Git checkout; omit `--baseline-ref` to measure only the
current implementation. The benchmark emits JSON with the runtime, revision,
timings and function-call counts.

Each benchmark scene contains only identical RB9 stirrups, translated along
X, sharing one prototype. A fresh `QuantityCache` is created for every
`collect_objects()` measurement. The quantity samples are three collections
in one process, not three fresh application launches. The selection sample
calls `Scene.select()` followed by `BimPanel.refresh(force=False)` fifty times.
Function-call wrappers count quantity calculations and mesh copies.

**Scope: CPU quantity collection, offscreen table construction and selection
notifications. These measurements do not include picking, OpenGL rendering,
event-loop painting, visible-highlight latency or FPS.**

### Recorded environment

The following results were measured on 22 October 2026 from the patched
working tree based on commit
`2daee48d4760cb4b6cbc406d11e8fbf0b9c07d1d`:

- Linux 6.18.55, x86_64, glibc 2.39.
- Runner exposed 9 logical CPUs; no physical CPU-model or GPU performance
  claim is made.
- Python 3.12.14, PySide6 6.12.0, Qt 6.12.0, Qt `offscreen` platform.
- `time.perf_counter_ns()` timing, including lightweight counter wrappers.
- Patched files were uncommitted at measurement time.

### Patched implementation

Construction and table-construction values are single measurements; quantity
collection values are medians of three samples. Selection values are medians
of fifty samples.

| Instances | Component construction | Fresh quantity collection | Cold BIM panel construction | Selection + BIM notification |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 59.28 ms | 54.11 ms | 58.36 ms | 0.00954 ms |
| 1,000 | 57.48 ms | 54.42 ms | 57.64 ms | 0.00934 ms |
| 10,000 | 176.33 ms | 108.06 ms | 153.50 ms | 0.01145 ms |

At all three sizes, each fresh collection called area and volume measurement
once and created **zero** world/transformed mesh copies. All fifty
selection-only notifications performed **zero** quantity collections, area
calculations, volume calculations or mesh copies. Existing table-row objects
were preserved. Selection-notification P95 was 0.01557, 0.01161 and 0.02436 ms
respectively; this remains a notification measurement, not click latency.

### Controlled 19-instance baseline

The benchmark loads the original `core/bim.py` from the pinned commit into an
isolated module and compares both collectors on the **same shared-component
scene**. This isolates quantity-collection behavior. It does not compare the
original world-baked generator with the new generator or run the entire old
application. The old collector is never run on the 10,000-object case.

| Per collection, 19 identical components | Original collector | Patched collector |
| --- | ---: | ---: |
| Median elapsed time, three samples | 1,654.92 ms | 50.40 ms |
| Volume calculations | 19 | 1 |
| `world_mesh()` calls | 19 | 0 |
| `transformed_mesh()` calls | 19 | 0 |

Timing varies with the host and workload. The call counts show the structural
improvement: repeated translations reuse one prototype measurement, and a
selection-only change does not rebuild the BIM takeoff table. Content edits,
document replacement and explicit refreshes still update the quantities.

## Persistence and export limits

Native `.igz` files preserve shared prototypes, transforms, object identities
and centreline metadata. Mesh or metadata edits invalidate the verified
display proxy; unsupported or stale data falls back to the solid. See the
[display guide](rebar-display.md) for supported interactions and material modes.

The current IFC class whitelist does not include `IfcReinforcingBar`. Such
tagged bars therefore continue to export as `IfcBuildingElementProxy`; this
change does not add native IFC reinforcement entities or a bending schedule.
The exporter uses each component's world placement, while viewport LOD never
substitutes centreline geometry into an export.

## Validation of this change

The final focused regression run passed **49 tests**, including six tests
using an actual OpenGL context under Xvfb/Mesa. It covered component sharing,
native persistence, BIM quantities, cache invalidation, picking, navigation,
transform previews, image export and shadow reuse. Pixel checks also verified
that the first centreline frame removes the old solid silhouette, the complete
beam's reinforcement remains visible through translucent concrete, and ending
the drag restores the original solid image.

```bash
xvfb-run -a python -m pytest -q \
  tests/test_bim_selection_cache.py tests/test_bounds_selection_cache.py \
  tests/test_pick_selection_cache.py tests/test_rebar_component_demo.py \
  tests/test_rebar_interaction_lod.py tests/test_rebar_lod_gl.py \
  tests/test_shadow_map_reuse.py
```

Use `QT_QPA_PLATFORM=xcb` for that Linux virtual-display run. An offscreen
platform cannot replace the actual graphics checks.

The broader checks have environment limits and are not reported as a clean
single-invocation full-suite pass:

- The repository-wide `python -m pytest -m "not slow"` command stopped at
  collection with seven errors in the extension/example tests: missing
  `openpyxl` and unresolved extension import paths.
- The explicit host run, `python -m pytest -q tests -m "not slow"`, collected
  3,626 tests. The process was killed at 3,333 recorded results (exit 137;
  the runner reported an out-of-memory kill). The remaining files were run
  separately: 293 passed, one skipped and one socket-dependent failure.
- Six existing socket-dependent tests across the two batches failed under
  the restricted runner. All six passed together when temporary local IPC
  sockets were permitted. No application code was changed to suppress them.
- The final focused run above includes the additional opacity and complete-beam
  graphics regressions added after the large host run started.

Physical Windows/GPU frame rate and complete click-to-highlight latency still
need measurement on representative user hardware and models.
