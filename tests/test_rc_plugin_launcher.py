"""The dev launcher stages into disposable data, never the installed plugin."""
import importlib.util
from pathlib import Path


def test_rc_launcher_isolates_data_and_cleans_only_its_temporary_directory(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "start_rc_plugin_dev.py"
    spec = importlib.util.spec_from_file_location("rc_dev_launcher", script)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setenv("APPDATA", "original-user-data")
    captured = []

    def fake_call(command, *, cwd, env):
        temporary = Path(env["APPDATA"])
        captured.append(temporary)
        assert env["LOCALAPPDATA"] == env["XDG_DATA_HOME"] == str(temporary)
        assert env["XDG_CONFIG_HOME"] == str(temporary)
        package = temporary / "ingetrazo" / "plugins" / "go_rc_detailing"
        source = cwd / "extensions" / "go-rc-detailing" / "go_rc_detailing"
        assert (package / "__init__.py").read_bytes() == (source / "__init__.py").read_bytes()
        assert len(list(package.rglob("*.py"))) == 47
        assert not list(package.rglob("*.pyc"))
        assert command[-1] == "--child"
        return 7

    monkeypatch.setattr(launcher.subprocess, "call", fake_call)
    assert launcher.main() == 7
    assert launcher.os.environ["APPDATA"] == "original-user-data"
    assert not captured[0].exists()
