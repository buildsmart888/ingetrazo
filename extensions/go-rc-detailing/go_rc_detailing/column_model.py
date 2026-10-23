"""Backward-compatible public facade for GO RC Column v0.10.3.

Implementation now lives in modules.column; this file is intentionally tiny.
No dynamic AST execution or duplicate column modeling code.
"""
from __future__ import annotations
from .modules.column.params import ColumnParams, check_params
from .modules.column.builder import create_column

__all__ = ["ColumnParams", "check_params", "create_column"]
