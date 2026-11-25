import importlib
import sys
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def make_package(tmp_path, monkeypatch):
    """Create a uniquely named package on sys.path from a mapping of relative path -> source."""
    created: list[str] = []

    def _make(files: dict[str, str]) -> tuple[str, Path]:
        name = f"qtr_pkg_{uuid.uuid4().hex[:8]}"
        root = tmp_path / name
        root.mkdir()
        (root / "__init__.py").write_text("")
        for relative, source in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        monkeypatch.syspath_prepend(str(tmp_path))
        importlib.invalidate_caches()
        created.append(name)
        return name, root.resolve()

    yield _make

    for name in created:
        for module in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
            del sys.modules[module]


@pytest.fixture
def make_reloader(qtbot):
    """Create a HotReloader with a short reload delay."""
    from qtreload.reloader import HotReloader

    created = []

    def _make(modules=(), messages=None, **kwargs):
        reloader = HotReloader(
            modules, log_func=messages.append if messages is not None else None, delay_ms=10, **kwargs
        )
        created.append(reloader)
        return reloader

    yield _make
    for reloader in created:
        reloader.deleteLater()


@pytest.fixture(scope="session", autouse=True)
def isolated_settings(tmp_path_factory):
    """Store QSettings in a temporary directory, so tests never touch the user's settings."""
    from qtpy.QtCore import QSettings

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))


@pytest.fixture
def settings_key():
    """Unique settings key, so tests do not share remembered state."""
    return f"test_{uuid.uuid4().hex[:8]}"
