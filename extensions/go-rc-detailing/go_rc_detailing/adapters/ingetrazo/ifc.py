"""IFC4 adapter delegates only to IngeTrazo native serialization."""
from __future__ import annotations


def export_beam(groups, target, bars, formwork):
    from ...native_ifc import export_beam_native
    return export_beam_native(groups, target, bars, formwork)


def export_column(parent, target, bars, formwork, identifier):
    from ...native_ifc import export_column_native
    return export_column_native(parent, target, bars, formwork, identifier)
