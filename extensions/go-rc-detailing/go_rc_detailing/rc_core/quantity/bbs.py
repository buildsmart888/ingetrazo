"""Pure Python preliminary BBS calculator shared across RC element types.

GO shape IDs are NOT national/international approved shape codes.
The modelled polygonal centerline length is NOT shop cutting length.
Use real paths in the input: never infer hooked-bar lengths from AABB/IFC.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
STEEL_DENSITY_KG_M3 = 7850.0


def bar_mass_kg_per_m(diameter_mm: float, density_kg_m3: float = STEEL_DENSITY_KG_M3) -> float:
    if diameter_mm <= 0 or density_kg_m3 <= 0:
        raise ValueError("steel diameter and density must be positive")
    d = diameter_mm / 1000.0
    return density_kg_m3 * math.pi * d * d / 4.0


def bar_mass_kg(diameter_mm: float, centerline_length_m: float,
                density_kg_m3: float = STEEL_DENSITY_KG_M3) -> float:
    if centerline_length_m < 0 or not math.isfinite(centerline_length_m):
        raise ValueError("bar centreline length must be finite and non-negative")
    return bar_mass_kg_per_m(diameter_mm, density_kg_m3) * centerline_length_m


@dataclass(frozen=True, slots=True)
class RebarRecord:
    bar_id: str
    mark: str
    kind: str
    diameter_mm: float
    centerline_length_m: float
    centerline_bend_radius_mm: float
    shape_code: str
    hook_angle_deg: int | None = None
    hook_straight_tail_mm: float = 0

    @property
    def theoretical_mass_kg(self) -> float:
        return bar_mass_kg(self.diameter_mm, self.centerline_length_m)


def group_bars(bars: list[RebarRecord]) -> list[dict]:
    """Create a grouped per-mark BBS, without assuming IFC BarLength."""
    groups: dict[tuple, dict] = {}
    for b in bars:
        key=(b.mark,b.shape_code,b.diameter_mm,b.centerline_length_m,b.centerline_bend_radius_mm,
             b.hook_angle_deg,b.hook_straight_tail_mm)
        if key not in groups:
            groups[key]={"mark":b.mark,"kind":b.kind,"shape_code":b.shape_code,
                         "diameter_mm":b.diameter_mm,"count":0,
                         "length_each_m":b.centerline_length_m,"total_length_m":0.0,
                         "weight_kg":0.0,"bend_radius_centerline_mm":b.centerline_bend_radius_mm,
                         "hook_angle_deg":b.hook_angle_deg,
                         "hook_straight_tail_mm":b.hook_straight_tail_mm,
                         "status":"PRELIMINARY, NOT FOR FABRICATION"}
        row=groups[key]
        row["count"]+=1
        row["total_length_m"]+=b.centerline_length_m
        row["weight_kg"]+=b.theoretical_mass_kg
    return list(groups.values())


def bbs_rows_from_legacy(bar_geom: list[dict], bar_meta: dict[str,dict], *,
                         beam_id: str, stirrup_angle_deg: int,
                         stirrup_radius_m: float, density_kg_m3: float = STEEL_DENSITY_KG_M3) -> list[dict]:
    """Mirror frozen v0.7 _build_bbs_verified_rows exactly (including rounding)."""
    out=[]
    for b in bar_geom:
        meta=bar_meta[b['name']]
        d=meta['diameter_mm']
        radius=(stirrup_radius_m*1000 if b['kind']=='stirrup'
                else float(meta.get('bend_radius_centerline_mm',meta.get('bend_radius_m',0)*1000)))
        poly=meta['length_m']
        shape={'top':'GO-M90','bottom':'GO-M90','extra_top':'GO-ET90',
               'extra_bottom':'GO-EB90','stirrup':f'GO-ST{stirrup_angle_deg}'}[b['kind']]
        out.append({'beam':beam_id,'bar':b['name'],'mark':meta['mark'],
            'shape_code_project_only':shape,'kind':b['kind'],'diameter_mm':d,
            'bend_radius_centerline_mm':round(radius,3),
            'straight_hook_tail_mm':meta.get('tail_straight_after_bend_mm',
                meta.get('hook_straight_extension_mm',
                    round(meta.get('hook_length_nominal_m',0.)*1000,3))),
            'hook_angle_deg':meta['hook_deg'],
            'number_of_bent_ends':2 if b['kind']!='stirrup' else 2,
            'calculated_centerline_cut_length_mm':round(poly*1000,3),
            'theoretical_mass_kg':round(meta['weight_kg'],6),
            'kg_per_m':round(bar_mass_kg_per_m(d,density_kg_m3),6),
            'fabrication_status':'PRELIMINARY: bend allowances and code need approval',
            'model_stirrup_nonplanar':b['kind']=='stirrup'})
    return out


def helix_centerline_length_m(radius_m: float, turns: int, rise_m: float) -> float:
    """Ideal helix length; no starter wraps, anchors, or shop bend allowances."""
    if radius_m <= 0 or turns < 1 or rise_m < 0:
        raise ValueError("helix radius, turns and rise must be valid")
    return math.hypot(2*math.pi*radius_m*turns,rise_m)
