# RB9 shared-component console demo

## Run

1. Open a new IngeTrazo document.
2. Choose **Extensions → Python Console → Run script file…**.
3. Select `scripts/GO_RB9_Stirrup_Fix.py` from this checkout.

The console supplies the active scene and wraps the run in one undo step.
Running the script again replaces only objects named with the
`GO_RB9FIX_` prefix; unrelated objects and their selection are retained.
Parameters at the top of the script use metres.

## What it creates

- One 3.0 × 0.20 × 0.40 m translucent beam.
- Three red upper DB12 bars and two orange lower DB12 bars.
- Nineteen blue RB9 stirrups, with the same continuous bent-hook geometry as
  the earlier demo, placed from X = 0.15 m through X = 2.85 m at 0.15 m spacing.

All stirrups reference one local mesh; each has its own placement matrix,
identity, name and IFC tag. They also share one immutable centreline metadata
block, so the first interactive frame validates and packs their path once.
The straight bars share one mesh per colour.
There are **25 objects, 4 unique meshes and 2,316 stored triangle faces**.
Displaying all placements in full detail still represents **41,676 triangles**
before visibility culling. Sharing reduces duplicate geometry; it does not
remove the GPU work of drawing every visible placement.

Moving a component changes its matrix. Editing shared component geometry
affects its copies; use **Make Unique** before an individual shape variation.
Native `.igz` saving preserves the shared prototypes and per-instance data.

## Interactive centreline display

With the accompanying host changes installed, the script attaches a local
centreline and a mesh signature using `core.rebar_display.attach_centerline`.
The renderer can use that cached line during interaction without replacing
the model's full mesh, changing BIM tags, or reducing export geometry.

An older host can run the script and create shared components, but cannot
provide the new automatic centreline display. After updating the application,
rerun the script so the new helper records a verified mesh signature.

If geometry is edited manually, the saved centreline may no longer describe
it. The renderer validates the signature and falls back to full geometry
instead of drawing an outdated line. Regenerate the bar to update its path.

## Geometry and validation scope

Bend radius, hook tails and the small out-of-plane hook offset are editable
example values. The demo preserves the earlier beam/bar coordinates, including
the zero longitudinal end cover. It does not establish reinforcement-code
compliance. Changed dimensions require a fresh clearance check.

Regression tests in `tests/test_rebar_component_demo.py` verify shared mesh
identity, independent object IDs, closed positive-volume geometry, transformed
face coordinates, safe replacement, native save/reopen, centreline signatures,
and moving a copy without changing the shared vertices. They do not measure
interactive frame rate on a physical workstation.
