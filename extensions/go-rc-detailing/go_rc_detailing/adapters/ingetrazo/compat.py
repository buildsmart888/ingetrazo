"""Host capability gates for the GO RC plugin."""
from __future__ import annotations


def require_supported_host(api_version=None):
    from core.bim import IFC_CLASSES
    from core.version import __version__
    if api_version is None:
        from views.extension_api import API_VERSION as api_version
    from ...native_ifc import require_native_bim
    if api_version < 2:
        raise RuntimeError("IngeTrazo Extension API_VERSION 2+ is required")
    require_native_bim()
    required = {"IfcReinforcingBar", "IfcColumn", "IfcBeam"}
    missing = required - set(IFC_CLASSES)
    if missing:
        raise RuntimeError(f"IngeTrazo {__version__} missing BIM classes: {sorted(missing)}")
    return __version__
