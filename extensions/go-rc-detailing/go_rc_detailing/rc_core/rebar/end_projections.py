"""Pure rebar extension geometry for vertical RC element connections.

The host column/slab/footing is *not* created by this calculation.  Its
responsibility is to locate the axial straight-leg tangent at a requested
projection beyond the concrete face.  The GO v0.10.0 zero-projection path is
preserved exactly, including the inside-column end inset.

No anchorage, lap, development length or engineering code check is implied.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class AxialEndStations:
    bottom_virtual_z_m: float
    top_virtual_z_m: float
    bottom_tangent_z_m: float
    top_tangent_z_m: float
    bottom_projection_m: float
    top_projection_m: float


def tangent_setback_m(bend_radius_m: float, tail_m: float) -> float:
    """Match locked-column fillet corner limiting: t=min(R, 0.5*(R+tail)).

    This is *not* a bend-tooling radius or bend-design acceptance result.
    The legacy geometry's fillet limits the tangent when the horizontal
    virtual leg is short; maintain that behaviour with any new projection.
    """
    if bend_radius_m <= 0 or tail_m < 0:
        raise ValueError("Bend radius must be >0 and hook tail must be >=0")
    return min(bend_radius_m, 0.5 * (bend_radius_m + tail_m))


def vertical_main_bar_stations(
    height_m: float,
    legacy_end_inset_m: float,
    top_projection_m: float = 0.0,
    bottom_projection_m: float = 0.0,
    *,
    top_hook: bool = False,
    bottom_hook: bool = False,
    bend_radius_m: float = 0.0,
    top_hook_tail_m: float = 0.0,
    bottom_hook_tail_m: float = 0.0,
) -> AxialEndStations:
    """Return column-local Z virtual corners and actual bend tangents.

    Column concrete occupies 0..height_m. Positive projection is measured
    beyond the respective CONCRETE FACE up to the straight-bar tangent:
    top face H + projection; bottom face 0 - projection. If no hook is
    selected the free end is precisely at that elevation. With a hook the
    virtual 90-degree corner lies one fillet setback farther out, so the
    *straight* vertical bar is still projected by exactly the requested mm.

    A zero projection is deliberate backwards compatibility: the main bar
    remains inside the original end-cover plane from v0.10.0.
    """
    vals=(height_m, legacy_end_inset_m, top_projection_m, bottom_projection_m,
          bend_radius_m, top_hook_tail_m, bottom_hook_tail_m)
    if not all(math.isfinite(float(x)) for x in vals):
        raise ValueError("Column extension geometry must be finite")
    if (height_m <= 0 or legacy_end_inset_m < 0
        or 2 * legacy_end_inset_m >= height_m
        or top_projection_m < 0 or bottom_projection_m < 0):
        raise ValueError("Invalid vertical column bar extent / projection")
    if top_hook or bottom_hook:
        if bend_radius_m <= 0:
            raise ValueError("Hooked column bars require a positive bend radius")
    bottom_virtual=legacy_end_inset_m
    top_virtual=height_m-legacy_end_inset_m
    bottom_setback=(tangent_setback_m(bend_radius_m,bottom_hook_tail_m)
                    if bottom_hook else 0.0)
    top_setback=(tangent_setback_m(bend_radius_m,top_hook_tail_m)
                 if top_hook else 0.0)
    if bottom_projection_m > 0:
        bottom_virtual=-bottom_projection_m-bottom_setback
    if top_projection_m > 0:
        top_virtual=height_m+top_projection_m+top_setback
    if top_virtual-bottom_virtual <= 2*bend_radius_m:
        if top_hook or bottom_hook:
            raise ValueError("Column too short for selected bar hooks")
    return AxialEndStations(
        bottom_virtual_z_m=bottom_virtual,
        top_virtual_z_m=top_virtual,
        bottom_tangent_z_m=bottom_virtual+bottom_setback,
        top_tangent_z_m=top_virtual-top_setback,
        bottom_projection_m=bottom_projection_m,
        top_projection_m=top_projection_m,
    )
