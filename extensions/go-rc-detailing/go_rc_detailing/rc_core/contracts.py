"""Stable, host-independent DTO contract for future RC modules.

All coordinates/dimensions are metres (except explicit diameter_mm), all
masses are kilograms. Structures can be mapped to IngeTrazo by an adapter.
This layer neither models code compliance nor writes an IFC file.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol,Any
from .geometry import Vec3,path_length
from .quantity import bar_mass_kg


class RCElementKind(str,Enum):
    BEAM='beam'
    COLUMN='column'
    SLAB='slab'
    FOUNDATION='foundation'
    STAIR='stair'
    WALL='wall'


@dataclass(frozen=True,slots=True)
class RebarDTO:
    bar_id: str
    mark: str
    diameter_mm: float
    points: tuple[Vec3,...]
    bend_radius_m: float
    shape_code: str  # project-only GO IDs, not standard fabrication shape codes

    def __post_init__(self):
        if not self.bar_id or not self.mark or self.diameter_mm<=0:
            raise ValueError('Each bar needs an ID, mark and positive diameter')
        if len(self.points)<2 or self.bend_radius_m<0:
            raise ValueError('Bar needs >=2 centerline points, radius >=0')

    @property
    def theoretical_length_m(self) -> float:
        return path_length(self.points)

    @property
    def theoretical_mass_kg(self) -> float:
        return bar_mass_kg(self.diameter_mm,self.theoretical_length_m)


@dataclass(frozen=True,slots=True)
class RCModelPlan:
    element_id: str
    element_kind: RCElementKind
    rebar: tuple[RebarDTO,...]
    concrete_gross_m3: float
    formwork_contact_m2: float
    warnings: tuple[str,...] = ()

    def __post_init__(self):
        if not self.element_id or self.concrete_gross_m3<0 or self.formwork_contact_m2<0:
            raise ValueError('Invalid element model plan')


class RCBuilder(Protocol):
    """Any RC element builder implements build(input) -> RCModelPlan."""
    def build(self, parameters: Any) -> RCModelPlan: ...
