"""Reusable 90-degree bent main/special reinforcement paths.

Schematic geometric centerlines; no development, splice or bend tool checks.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from ..geometry.vector import Vec3
from ..geometry.fillet import fillet_path


def bend_setback_m(radius_m: float, angle_deg: float) -> float:
    """v0.7 virtual-corner tangent setback (R * tan(turn_angle / 2))."""
    if radius_m <= 0 or not 0 < angle_deg < 180:
        raise ValueError("radius and turn angle must be positive and less than 180 degrees")
    return radius_m * math.tan(math.radians(angle_deg / 2))


@dataclass(frozen=True, slots=True)
class Hook90Spec:
    x0_m: float
    x1_m: float
    z_m: float
    direction: int  # +1 up, -1 down
    radius_m: float
    straight_tail_m: float
    segments: int = 10

    def validate(self) -> None:
        if self.direction not in (-1, 1):
            raise ValueError("hook direction must be +1 or -1")
        if self.radius_m <= 0 or self.straight_tail_m < 0:
            raise ValueError("hook radius must be positive, straight tail cannot be negative")
        if self.x1_m-self.x0_m <= 2*self.radius_m+0.015:
            raise ValueError("bar span too short for two rounded 90 degree ends")


def bar_with_90_hooks(spec: Hook90Spec) -> tuple[list[Vec3], list[Vec3]]:
    """Returns virtual control path and accepted-style polygonal rounded path."""
    spec.validate()
    reach=spec.radius_m+spec.straight_tail_m
    control=[Vec3(spec.x0_m,0,spec.z_m+spec.direction*reach),
             Vec3(spec.x0_m,0,spec.z_m),
             Vec3(spec.x1_m,0,spec.z_m),
             Vec3(spec.x1_m,0,spec.z_m+spec.direction*reach)]
    bent=fillet_path(control,spec.radius_m,spec.segments)
    if len(bent)<4:
        raise ValueError("90 degree bend centerline is degenerate")
    if abs((bent[1]-bent[0]).length()-spec.straight_tail_m) > 0.001:
        raise ValueError("topological bend changed straight tail length")
    if abs((bent[-1]-bent[-2]).length()-spec.straight_tail_m) > 0.001:
        raise ValueError("topological bend changed straight tail length")
    return control, bent
