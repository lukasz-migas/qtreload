import pytest

from qtreload.config import ReloadConfig, find_pyproject, load_config
from qtreload.reloader import PY_IGNORE_PATTERN, PY_PATTERN, RELOAD_DELAY_MS, STYLESHEET_PATTERN, HotReloader


def _write_pyproject(directory, table):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyproject.toml").write_text(f"[project]\nname = 'x'\n\n{table}")
    return directory / "pyproject.toml"


def test_defaults(tmp_path):
    config = load_config(tmp_path, environ={})
    assert config == ReloadConfig()
    assert config.py_pattern == PY_PATTERN
    assert config.ignore_py_pattern == PY_IGNORE_PATTERN
    assert config.stylesheet_pattern == STYLESHEET_PATTERN
    assert config.delay_ms == RELOAD_DELAY_MS


def test_pyproject_found_in_parent_with_table(tmp_path):
    root = _write_pyproject(
        tmp_path,
        '[tool.qtreload]\nmodules = ["app", " plugin ", "app"]\nignore_py_pattern = []\ndelay_ms = 100\n',
    )
    nested = tmp_path / "src" / "app"
    _write_pyproject(nested, "[tool.ruff]\nline-length = 100\n")  # nearer, but without [tool.qtreload]

    assert find_pyproject(nested) == root
    config = load_config(nested, environ={})
    assert config.modules == ("app", "plugin")
    assert config.ignore_py_pattern == ()
    assert config.py_pattern == PY_PATTERN
    assert config.delay_ms == 100


def test_environment_overrides_pyproject(tmp_path):
    _write_pyproject(tmp_path, '[tool.qtreload]\nmodules = ["app"]\npy_pattern = ["*.py"]\n')
    environ = {
        "QTRELOAD_HOT_RELOAD_MODULES": "other, more,",
        "QTRELOAD_IGNORE_PY_PATTERN": "",
        "QTRELOAD_STYLESHEET_PATTERN": "**/*.qss,**/*.css",
        "QTRELOAD_DELAY_MS": "50",
    }
    config = load_config(tmp_path, environ=environ)
    assert config.modules == ("other", "more")
    assert config.py_pattern == ("*.py",)
    assert config.ignore_py_pattern == ()
    assert config.stylesheet_pattern == ("**/*.qss", "**/*.css")
    assert config.delay_ms == 50


@pytest.mark.parametrize(
    "table, message",
    [
        ('modulse = ["app"]', "Unknown key 'modulse'"),
        ('modules = "app"', "must be a list of strings"),
        ("py_pattern = [1]", "must be a list of strings"),
        ("delay_ms = true", "non-negative integer"),
        ("delay_ms = -1", "non-negative integer"),
    ],
)
def test_invalid_pyproject(tmp_path, table, message):
    _write_pyproject(tmp_path, f"[tool.qtreload]\n{table}\n")
    with pytest.raises(ValueError, match=message):
        load_config(tmp_path, environ={})


@pytest.mark.parametrize("value", ["soon", "-5"])
def test_invalid_environment_delay(tmp_path, value):
    with pytest.raises(ValueError, match="QTRELOAD_DELAY_MS"):
        load_config(tmp_path, environ={"QTRELOAD_DELAY_MS": value})


def test_broken_pyproject_is_ignored(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.qtreload\nmodules = ")
    assert load_config(tmp_path, environ={}) == ReloadConfig()


def test_reloader_from_config(qtbot, make_package, settings_key):
    name, root = make_package({"a.py": "", "b.py": ""})
    config = ReloadConfig(modules=(name,), py_pattern=("a.py",), delay_ms=42)
    reloader = HotReloader.from_config(config)
    assert reloader.modules == (name,)
    assert reloader.files == [str(root / "a.py")]
    assert reloader._reload_timer.interval() == 42

    reloader = HotReloader.from_config(config, delay_ms=7, settings_key=settings_key)
    assert reloader._reload_timer.interval() == 7
    assert reloader.settings_key == settings_key


def test_install_hot_reload_uses_config(qtbot, make_package, tmp_path, monkeypatch):
    from qtreload import install

    name, root = make_package({"a.py": "", "b.py": ""})
    project = tmp_path / "project"
    _write_pyproject(project, f'[tool.qtreload]\nmodules = ["{name}"]\npy_pattern = ["a.py"]\n')
    monkeypatch.chdir(project)
    monkeypatch.setenv("QTRELOAD_HOT_RELOAD", "1")
    monkeypatch.delenv("QTRELOAD_HOT_RELOAD_MODULES", raising=False)
    monkeypatch.setenv("QTRELOAD_DELAY_MS", "25")
    monkeypatch.setattr(install, "_reload_ref", None)

    widget = install.install_hot_reload()
    qtbot.addWidget(widget)
    assert widget.reloader.modules == (name,)
    assert widget.reloader.files == [str(root / "a.py")]
    assert widget.reloader._reload_timer.interval() == 25

    monkeypatch.setenv("QTRELOAD_PY_PATTERN", "b.py")
    assert install.install_hot_reload() is widget
    assert widget.reloader.files == [str(root / "b.py")]
