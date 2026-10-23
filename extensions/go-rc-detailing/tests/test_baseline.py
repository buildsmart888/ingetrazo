"""Migration acceptance checks for the captured deployed RC package."""
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from core.extensions import _import_by_path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "go_rc_detailing"


def test_imported_snapshot_has_exact_file_set_and_hashes():
    manifest = json.loads((ROOT / "baseline-manifest.json").read_text("utf-8"))
    actual = {
        path.relative_to(PACKAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.rglob("*.py")
    }
    assert len(actual) == manifest["file_count"] == 47
    assert actual == manifest["files"]
    assert actual["beam_baseline_v0_7.py"] == manifest["locked_beam_baseline_sha256"]


def test_native_loader_host_contract_and_locked_beam():
    plugin = _import_by_path("go_rc_detailing", PACKAGE / "__init__.py")
    assert callable(plugin.setup)
    compat = importlib.import_module(plugin.__name__ + ".adapters.ingetrazo.compat")
    assert compat.require_supported_host(2) == "0.5.9"
    with pytest.raises(RuntimeError, match="API_VERSION 2"):
        compat.require_supported_host(1)
    adapter = importlib.import_module(plugin.__name__ + ".beam_adapter")
    adapter.assert_baseline_locked()
