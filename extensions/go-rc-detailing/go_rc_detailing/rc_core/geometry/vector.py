"""3-D vector compatible with the v0.7 QVector3D arithmetic, without Qt.

For geometric parity, accessors intentionally use Qt-style x(), y(), z().
Coordinates are in metres, stored as Python floats.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Vec3:
    _x: float
    _y: float
    _z: float = 0.0

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y

    def z(self) -> float:
        return self._z

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self._x + other._x, self._y + other._y, self._z + other._z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self._x - other._x, self._y - other._y, self._z - other._z)

    def __mul__(self, value: float) -> Vec3:
        return Vec3(self._x * value, self._y * value, self._z * value)

    __rmul__ = __mul__

    def __truediv__(self, value: float) -> Vec3:
        return self * (1.0 / value)

    def length(self) -> float:
        return math.sqrt(self._x**2 + self._y**2 + self._z**2)

    def normalized(self) -> Vec3:
        magnitude = self.length()
        return self / magnitude if magnitude > 1e-12 else Vec3(0, 0, 0)

    def tuple(self) -> tuple[float, float, float]:
        return self._x, self._y, self._z

    @staticmethod
    def dotProduct(a: Vec3, b: Vec3) -> float:
        return a._x*b._x + a._y*b._y + a._z*b._z

    @staticmethod
    def crossProduct(a: Vec3, b: Vec3) -> Vec3:
        return Vec3(a._y*b._z-a._z*b._y, a._z*b._x-a._x*b._z, a._x*b._y-a._y*b._x)


def as_vec3(point) -> Vec3:
    """Convert Qt-like vector or sequence, without importing Qt."""
    if isinstance(point, Vec3):
        return point
    if callable(getattr(point, "x", None)):
        return Vec3(float(point.x()), float(point.y()), float(point.z()))
    return Vec3(float(point[0]), float(point[1]), float(point[2]))
