import importlib
import logging

from qtpy.QtCore import QSettings

from qtreload.reloader import SETTINGS_ORGANIZATION


def _settings(key):
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_ORGANIZATION, key)


def test_edits_are_remembered_per_field(make_reloader, make_package, settings_key):
    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    reloader = make_reloader([name_a], settings_key=settings_key)
    reloader.add_module(name_b)
    reloader.remove_modules([name_a])

    # only the modules were edited - the patterns passed next time still apply
    again = make_reloader([name_a], settings_key=settings_key, py_pattern=("none.py",))
    assert again.modules == (name_b,)
    assert again.py_pattern == ("none.py",)
    assert any("Using remembered modules" in msg for msg, _ in again.messages)

    again.set_patterns(stylesheet_pattern=("**/*.css",))
    third = make_reloader([name_a], settings_key=settings_key)
    assert third.stylesheet_pattern == ("**/*.css",)
    assert third.modules == (name_b,)


def test_without_settings_key_nothing_is_remembered(make_reloader, make_package):
    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    reloader = make_reloader([name_a])
    reloader.add_module(name_b)
    assert reloader.settings_key is None
    assert make_reloader([name_a]).modules == (name_a,)


def test_reset_settings(make_reloader, make_package, settings_key):
    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    reloader = make_reloader([name_a], settings_key=settings_key)
    reloader.replace_modules([name_b])
    reloader.set_patterns(py_pattern=("b.py",))
    reloader.set_paused(True)

    reloader.reset_settings()
    assert reloader.modules == (name_a,)
    assert reloader.py_pattern == ("**/*.py",)
    assert not reloader.paused
    assert _settings(settings_key).allKeys() == [], "Reset must not save the configured values"
    assert make_reloader([name_a], settings_key=settings_key, py_pattern=("x",)).py_pattern == ("x",)


def test_paused_state_is_remembered(make_reloader, settings_key):
    reloader = make_reloader(settings_key=settings_key)
    reloader.set_paused(True)
    again = make_reloader(settings_key=settings_key)
    assert again.paused
    assert any("paused" in msg and level == logging.WARNING for msg, level in again.messages)


def test_invalid_remembered_values_are_ignored(make_reloader, make_package, settings_key):
    name, _ = make_package({"a.py": ""})
    settings = _settings(settings_key)
    settings.setValue("modules", "not json")
    settings.setValue("py_pattern", "[1, 2]")
    settings.setValue("paused", '"yes"')
    settings.sync()

    reloader = make_reloader([name], settings_key=settings_key)
    assert reloader.modules == (name,)
    assert reloader.py_pattern == ("**/*.py",)
    assert not reloader.paused
    warnings = [msg for msg, level in reloader.messages if level == logging.WARNING]
    assert sum("Ignoring invalid remembered value" in msg for msg in warnings) == 3


def test_paused_changes_are_ignored(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    emitted, paused_states = [], []
    reloader.evt_pyfile.connect(emitted.append)
    reloader.evt_paused_changed.connect(paused_states.append)

    reloader.on_reload_file(str(root / "a.py"))  # pending when paused - dropped
    reloader.set_paused(True)
    reloader.set_paused(True)
    (root / "a.py").write_text("def value():\n    return 2\n")
    reloader.on_reload_file(str(root / "a.py"))
    (root / "new.py").write_text("")
    reloader.on_directory_changed(str(root))
    qtbot.wait(50)
    assert emitted == []
    assert mod.value() == 1
    assert str(root / "new.py") not in reloader.files

    reloader.set_paused(False)
    assert paused_states == [True, False]
    assert str(root / "new.py") in reloader.files, "New files are discovered on resume"
    assert any("1 changed files were not reloaded" in msg for msg, _ in reloader.messages)

    # a change event for a file modified during the pause can arrive late - it must not reload the file
    reloader.on_reload_file(str(root / "a.py"))
    qtbot.wait(50)
    assert emitted == [], (reloader._pause_window, (root / "a.py").stat().st_mtime)
    assert mod.value() == 1

    # files modified after resuming are reloaded
    (root / "a.py").write_text("def value():\n    return 3\n")
    with qtbot.waitSignal(reloader.evt_pyfile, timeout=2000):
        reloader.on_reload_file(str(root / "a.py"))
    assert mod.value() == 3

    reloader.set_paused(True)
    (root / "a.py").write_text("def value():\n    return 4\n")
    reloader.reload_path(str(root / "a.py"))
    assert mod.value() == 4, "Explicit reloads work while paused"


def test_widget_pause_and_reset_controls(qtbot, make_package, settings_key):
    from qtreload.qt_reload import QtReloadWidget

    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    widget = QtReloadWidget([name_a], delay_ms=123, settings_key=settings_key)
    qtbot.addWidget(widget)
    assert widget.reloader._reload_timer.interval() == 123
    assert not widget._reset_btn.isHidden()

    widget._pause_checkbox.setChecked(True)
    assert widget.reloader.paused
    widget.reloader.set_paused(False)
    assert not widget._pause_checkbox.isChecked()

    widget.reloader.add_module(name_b)
    widget._reset_btn.click()
    assert widget.reloader.modules == (name_a,)

    plain = QtReloadWidget([])
    qtbot.addWidget(plain)
    assert plain._reset_btn.isHidden()
