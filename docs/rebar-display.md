# Interactive reinforcement display

This implementation is ported onto the exact upstream IngeTrazo **v0.5.9**
release commit `24e7ada6df9f0b4f5f761f287aaade9e40e6728c`. It keeps v0.5.9's
lean/native instancing and inference/snap pipeline; the older 0.5.7
screen-context Select patch is intentionally not part of this port.

The viewport can display a verified centreline for reinforcement components
while navigating or transforming the model. The full solid remains the scene
geometry: selection, snapping, undo, quantities and file exports continue to
read the solid. No hidden flags, groups or mesh vertices are changed by LOD.

## Create compatible reinforcement

Run `scripts/GO_RB9_Stirrup_Fix.py` from the Python Console's **Run script
file** command. It makes a beam, five longitudinal bars and nineteen stirrups.
Each repeated bar shape shares its local mesh; its `QMatrix4x4` places it in
the model. The script replaces only its own `GO_RB9FIX_` groups.

Existing objects without centreline metadata still work and draw as solids.
Regenerate the demonstration with the updated script to attach the proxies;
merely naming an arbitrary group `IfcReinforcingBar` does not simplify it.

An extension can attach a proxy after building a local-space mesh:

```python
from PySide6.QtGui import QMatrix4x4
from core.group import Group
from core.rebar_display import attach_centerline

group = Group(prototype_mesh, name="RB9_01")
group.xform = QMatrix4x4()
group.xform.translate(0.15, 0.0, 0.0)
group.component = True
attach_centerline(
    group,
    points=local_centerline_points,
    diameter_m=0.009,
    definition_key="RB9_stirrup_type_A",
)
```

The points and mesh must use the same local coordinates. Place or rotate a
bar with its instance matrix; do not translate the shared mesh's vertices.

`attach_centerline` preserves other extension data and sets:

```python
group.ext["go_rebar"] = {
    "version": 1,
    "centerline": [[x, y, z], ...],
    "diameter_m": 0.009,
    "definition_key": "RB9_stirrup_type_A",
    "mesh_signature": "...",
}
```

The helper computes the signature from the actual mesh. Do not manufacture a
signature, use a serial counter as a persisted signature, or attach a path
that does not describe the solid. The digest is independent of vertex/face
insertion order, so it survives native `.igz` save/load. Standard mesh mutation
APIs advance the serial and invalidate the cached verification.

Treat the inner `go_rebar` block and its centreline as immutable. Identical
instances may share that block in memory, while their outer `ext` dictionaries
remain separate. A parametric rebuild should build/replace the mesh and call
`attach_centerline` again. Advance the scene's content version through the
normal command/transaction mechanism after a metadata or geometry edit.

## Display behavior

| Interaction | Representation |
| --- | --- |
| Orbit, pan, camera drag or mouse look | Cached centreline instances |
| Mouse wheel burst | Centreline; solid returns 180 ms after the last wheel event |
| Group move/rotate preview | Centreline at the frozen instance pose plus preview transform |
| Release of a camera drag | Full solid |
| Escape or focus loss | Full solid; stale camera drag/look state is cleared |
| Image export | Full solid |
| Group edit or active section cut | Full solid |
| Unsupported, malformed or stale proxy | Full solid |

The fast path requires an opaque instance eligible for the existing OpenGL
instanced renderer. Translucent/back-side materials, billboards, classic
world-space groups, and `INGETRAZO_NO_INSTANCING=1` use normal rendering.
Rebar children inside a containing group inherit their centreline metadata in
the viewport's world-placement proxy.

The line buffer is shared by definition. Instance matrices use the existing
instanced shader; there is no draw call per bar. Faces, ordinary mesh edges
and curved-surface silhouettes of a simplified bar are omitted from those
display passes. Precise picking is deliberately unchanged.

Camera/selection changes reuse the proxy cache. A content or preview change
reconciles GPU entries with live definitions and releases obsolete buffers.
Document reset/context teardown release all remaining line buffers.

## Verification

`tests/test_rebar_interaction_lod.py` covers verification/cache reuse, changed
geometry falling back to solids, malformed metadata, interaction transitions,
solid-pass suppression, instance batching, preview transforms, cache cleanup,
and the interaction/display cache transitions.

For an actual graphics run, check:

1. Create the demo in a new document and orbit/pan/zoom. Bars become single
   centreline polylines; concrete and other ordinary objects keep their style.
2. Release the drag or stop the wheel. The same solids return at the same poses.
3. Move and rotate one bar, cancel with Escape, then repeat and commit. Its
   stored mesh must stay shared and its final matrix must match the preview.
4. Switch to another window mid-gesture and return. No stuck orbit or line mode.
5. Save/open `.igz`, repeat navigation, and export a view while wheel LOD is
   active. The export must contain solids and the reopened bars must retain
   their local paths and shared meshes.
6. Edit a bar's mesh directly. Its old proxy must be rejected until the
   producer rebuilds and reattaches it. Test an active section and group edit.

A passing functional graphics test does not establish an FPS target on user
hardware. Measure cold/warm selection latency and frame time separately, with
representative numbers of instances and visible bars.
