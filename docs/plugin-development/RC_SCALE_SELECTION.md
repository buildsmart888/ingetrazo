# RC scale fixtures and selection memory work - 2026-10-24

This increment fixes two source-host selection paths and adds bounded native
scale replay. It does not establish smooth large-building interaction or
change the installed application.

## Reproducible fixtures

The source v0.10.3 four-specimen document is repeated as independent modules,
with unique native IDs, per-storey provenance and shared mesh prototypes.
These are stress fixtures, not a connected/engineered building: slabs, stairs,
joints and reinforcement design are not generated or validated.

| Storeys | Modules per storey | Bars | Groups including wires | Placed faces | Bar prototypes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 | 2 | 1,086 | 1,284 | 1,095,300 | 20 |
| 10 | 6 | 10,860 | 12,840 | 10,953,000 | 20 |

PASS: both native files were generated and save/open preserved counts, total
BBS mass and prototype sharing. Placement provenance retains source IDs.
Wires reuse the original batched wire meshes rather than duplicating their
geometry per storey. Source generation mathematics remains unchanged.

## Host fixes

1. `tools/select.py`: window/crossing selection first projects eight corners
   of each placed bounding box. Only proven fully-inside or fully-outside
   cases short-circuit. Partial overlap and points crossing the camera plane
   retain the previous exact geometry path. A bounding-box intersection alone
   never counts as a hit.
2. `views/viewport.py`: a leaf instance's selected outline computes its box
   from cached prototype points instead of asking for its baked world-space
   triangle/edge chunk. Per-placement box results follow mesh mutation,
   transforms and axes; selection-only changes reuse them. New/Open clears
   the cache with the other document caches. The bounded cache holds no mesh
   or group references.

These changes retain editable native objects and the existing exact oriented
box math. They do not change bar shape, centreline/BBS data or quantities.
They also do not provide Wire-to-individual-bar picking or a new navigation
LOD system.

## Validation and resource limit

PASS: 86 tests, one unrelated SKP export test deselected, 19.84 seconds in the
limited Qt 6.11.2 RC QA environment. The initial broader targeted run reported
85 passes and one failure because `openskp` was missing; it was not a full
suite pass. Tests cover box semantics, partial/near-camera cases, nested
instances, exact oriented boxes under rotation/nonuniform/mirrored scaling,
axes changes, geometry mutation, move/Undo and prototype-point reuse.

A headless test computes 10,000 selection boxes from one simple prototype
while forbidding placed-chunk construction. This proves the allocation path,
not rendering/selection performance of 10,000 real bars.

The earlier unmodified 1,086-bar native run stopped at window selection:
the guard observed 1,333.62 MB worker-tree private memory, 911 MB RSS and
347.35 MB machine memory available. This was a controlled memory-floor stop,
not evidence of an application crash or an independently measured freeze.

After the fixes, available machine memory was only 161-177 MB. Preflight
refused to start either large native worker (512 MB minimum startup headroom
for the configured 384 MB floor). Consequently **post-fix OpenGL click/box,
zoom and orbit acceptance remains NOT TESTED** at both sizes. No before/after
speed or memory-saving percentage is claimed. Other user processes were not
terminated. See [recorded evidence](evidence/rc-scale-20261024.json).

## Resume the native checks

Use a fresh output directory on each run, with other work saved and sufficient
available RAM (about 2 GB is a practical starting point, not a capacity promise).
The optional `psutil` QA dependency monitors only the launched worker tree.
On timeout/memory limits it stops those workers and preserves resource and
last-stage/partial-result reports. Parent cleanup waits for descendants to
release GPU cache files. A low-memory preflight starts no worker.

```powershell
python -m pip install -r requirements-rc-qa.txt
python scripts/rc_scale_models.py ../rc-specimens-new/four-rc-specimens.igz --output ../rc-scale-new
python scripts/rc_native_selection.py ../rc-scale-new/rc-1086-bars-3-storeys.igz --output ../rc-1086-native-new --modes solid --navigation --max-private-mb 1800 --min-free-mb 384 --timeout 180
python scripts/rc_native_selection.py ../rc-scale-new/rc-10860-bars-10-storeys.igz --output ../rc-10860-native-new --modes solid --navigation --max-private-mb 1800 --min-free-mb 384 --timeout 180
```

`--navigation` adds unselected orbit and wheel events. `--storey N` hides other
synthetic storeys **after opening**; it is a QA view filter and does not yet
reduce the initial load/first-frame cost. Solid-only scale runs avoid a
document-wide Wire rebuild. Other modes can be requested separately; their
scaling remains unvalidated. Physical mouse and packaged-host QA remain open.
