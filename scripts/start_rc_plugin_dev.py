"""Launch the source host with a disposable RC plugin installation."""
from pathlib import Path
import os
import runpy
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "extensions" / "go-rc-detailing" / "go_rc_detailing"
    with tempfile.TemporaryDirectory(prefix="ingetrazo-rc-dev-") as temporary:
        sandbox = Path(temporary)
        target = sandbox / "ingetrazo" / "plugins" / "go_rc_detailing"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = os.environ.copy()
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            env[key] = str(sandbox)
        print("Source host with disposable RC plugin:", target, flush=True)
        return subprocess.call(
            [sys.executable, str(Path(__file__).resolve()), "--child"], cwd=root, env=env
        )


if __name__ == "__main__":
    if sys.argv[1:] == ["--child"]:
        from PySide6.QtCore import QSettings

        QSettings.setDefaultFormat(QSettings.IniFormat)
        for scope in (QSettings.UserScope, QSettings.SystemScope):
            QSettings.setPath(QSettings.IniFormat, scope, os.environ["APPDATA"])
        host = Path(__file__).resolve().parents[1] / "main.py"
        sys.path.insert(0, str(host.parent))
        sys.argv = [str(host), "--new-window"]
        runpy.run_path(str(host), run_name="__main__")
        raise SystemExit(0)
    raise SystemExit(main())
