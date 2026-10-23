"""GO RC Detailing v0.10.3 Dual Display (Phase3+4) plus independent column main-bar projections native adapters / modular columns plugin for IngeTrazo 0.5.9+ (API_VERSION 2).

Native BIM / IFC, four-toolbar-action extension. Accepted GO RC Beam v0.7
geometry is byte-for-byte locked and is not modified by this release.
"""
from __future__ import annotations


def setup(app):
    if getattr(app, "api_version", 0) < 2:
        raise RuntimeError("GO RC Detailing requires IngeTrazo extension API_VERSION >= 2")
    from .adapters.ingetrazo.compat import require_supported_host
    require_supported_host(app.api_version)
    from .toolbar import install_toolbar
    install_toolbar(app)
    from .bim_panel import install_bim_panel
    install_bim_panel(app)
