"""BIM tagging stays native to core.bim, independent of module type."""
from __future__ import annotations


def tag_group(group, ifc_class: str, name: str, host_bim=None):
    # Injection of the host BIM service preserves headless testing, whereas
    # the live scope uses the actual core.bim module from IngeTrazo.
    if host_bim is None:
        from core import bim as host_bim
    supported = getattr(host_bim, "IFC_CLASSES", None)
    if supported is not None and ifc_class not in supported and ifc_class != "IfcBuildingElementProxy":
        raise ValueError(f"Unsupported native IFC class: {ifc_class}")
    host_bim.tag_group(group, ifc_class, name)
    return group
