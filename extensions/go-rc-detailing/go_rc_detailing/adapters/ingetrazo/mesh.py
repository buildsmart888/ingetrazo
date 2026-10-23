"""Mesh topology checks: keep them separate from beam/column centerlines."""
from __future__ import annotations
from ...geometry_adapter import assert_watertight, mesh_closed_report

__all__ = ["assert_watertight", "mesh_closed_report"]
