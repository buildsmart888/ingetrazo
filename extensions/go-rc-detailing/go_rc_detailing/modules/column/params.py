"""Column geometry parameters and input checks."""
from __future__ import annotations
from dataclasses import dataclass
import math
import re

@dataclass
class ColumnParams:
    shape: str = "rect"                # rect | circular
    column_id: str = "C1"
    width_mm: float = 300.0            # rect X
    depth_mm: float = 400.0            # rect Y
    diameter_mm: float = 400.0         # circular
    height_mm: float = 3000.0
    cover_mm: float = 40.0
    longitudinal_db_mm: float = 16.0
    bars_x: int = 2                    # rect: count along top and bottom
    bars_y: int = 2                    # rect: count along left and right
    circular_bar_count: int = 8
    tie_db_mm: float = 9.0
    tie_spacing_mm: float = 150.0
    tie_hook_deg: int = 135            # rectangular: 90 or 135
    tie_hook_tail_mm: float = 90.0
    first_tie_mm: float = 50.0         # from column bottom/top ends
    plywood_mm: float = 18.0
    show_formwork: bool = True
    export_ifc: bool = True
    pos_x_mm: float = 0.0
    pos_y_mm: float = 0.0
    pos_z_mm: float = 0.0
    # Individual main-bar 90 degree hooks. Zero defaults protect small columns.
    main_hook_top: bool = False
    main_hook_bottom: bool = False
    # Inward matches accepted v0.8.2. Outward splays hooks radially beyond
    # the column footprint: must be embedded in separately modelled concrete.
    main_hook_top_direction: str = "inward"     # inward | outward
    main_hook_bottom_direction: str = "inward"  # inward | outward
    main_hook_top_tail_mm: float = 40.0   # original v0.10.0 hook setting
    main_hook_bottom_tail_mm: float = 40.0
    # Positive values measure STRAIGHT bar projection beyond the concrete
    # TOP/BOTTOM face (to the bend tangent, if a 90-degree hook is enabled).
    # Zero preserves v0.10.0's accepted cover-inset end geometry exactly.
    main_top_projection_mm: float = 0.0
    main_bottom_projection_mm: float = 0.0
    spiral_segments_per_turn: int = 32
    # Native BIM visibility requires individual top-level tagged groups;
    # nested assemblies require the separate GO BIM Browser instead.
    native_bim_visible: bool = True


def check_params(p: ColumnParams):
    if p.shape not in ("rect", "circular"):
        raise ValueError("Column shape must be rect or circular")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", p.column_id):
        raise ValueError("Column ID must start with a letter; use A-Z, numbers, _, -")
    for field in ("height_mm", "cover_mm", "longitudinal_db_mm", "tie_db_mm",
                  "tie_spacing_mm", "first_tie_mm", "plywood_mm"):
        if float(getattr(p, field)) <= 0:
            raise ValueError(field + " must be positive")
    if p.height_mm <= 2 * (p.cover_mm + p.longitudinal_db_mm / 2):
        raise ValueError("Column height too small for end cover")
    for field in ("main_top_projection_mm", "main_bottom_projection_mm"):
        value = getattr(p, field)
        if not math.isfinite(float(value)) or not 0 <= value <= 5000:
            raise ValueError(field + " must be finite, between 0 and 5000 mm")
    if p.first_tie_mm < p.cover_mm + p.tie_db_mm / 2 + 1.0:
        raise ValueError("First hoop centre must be beyond cover + tie radius + 1 mm")
    if p.height_mm <= 2 * p.first_tie_mm:
        raise ValueError("First tie offsets exceed column height")
    for end in ("top", "bottom"):
        direction = getattr(p, "main_hook_" + end + "_direction")
        if direction not in ("inward", "outward"):
            raise ValueError(f"{end} hook direction must be inward or outward")
        if getattr(p, "main_hook_"+end) and not 20 <= getattr(p, "main_hook_"+end+"_tail_mm") <= 400:
            raise ValueError("Column main bar hook straight-tail length must be between 20 and 400 mm")
    if not 12 <= p.spiral_segments_per_turn <= 96:
        raise ValueError("Spiral segments/turn must be between 12 and 96")
    if p.shape == "rect":
        if p.tie_hook_deg not in (90, 135):
            raise ValueError("Rectangular tie hooks must be 90 or 135 degrees")
        if not (2 <= p.bars_x <= 12 and 2 <= p.bars_y <= 12):
            raise ValueError("Rectangular bars_x and bars_y must be 2..12")
        if min(p.width_mm, p.depth_mm) < 220:
            raise ValueError("Rectangular column minimum side is 220 mm in this prototype")
        if p.tie_hook_tail_mm < 60:
            raise ValueError("Tie straight hook tail must be >= 60 mm in this prototype")
    else:
        if not 6 <= p.circular_bar_count <= 40:
            raise ValueError("Circular bar count must be 6..40")
        if p.diameter_mm < 280:
            raise ValueError("Circular column diameter must be >= 280 mm in this prototype")
        if p.tie_spacing_mm < p.tie_db_mm + 2.0:
            raise ValueError("Spiral pitch must exceed bar diameter (plus 2 mm)")
    return p

