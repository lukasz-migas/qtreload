import os

from qtreload.utilities import path_to_module


def test_widget(qtbot):
    """Test widget."""
    from qtreload.qt_reload import QtReloadWidget

    widget = QtReloadWidget(["qtreload"])
    qtbot.addWidget(widget)
    assert widget is not None
    assert len(widget.path_to_index_map) > 0, "Expected more than 1 path"

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map.keys():
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"


def test_install_hot_reload(qtbot):
    """Test installing hot reload."""
    from qtreload.install import install_hot_reload

    os.environ["QTRELOAD_HOT_RELOAD"] = "0"
    widget = install_hot_reload(None)
    assert widget is None

    os.environ["QTRELOAD_HOT_RELOAD"] = "1"
    os.environ["QTRELOAD_HOT_RELOAD_MODULES"] = "qtreload"
    widget = install_hot_reload(None)
    qtbot.addWidget(widget)
    assert widget is not None
    assert len(widget.path_to_index_map) > 0, "Expected more than 1 path"
    assert len(widget._module_paths) == 1, "Expected 2 modules"

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map.keys():
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"
        paths = widget._get_file_paths(module)
        assert len(paths) > 0, "Expected more than 1 path"

    os.environ["QTRELOAD_HOT_RELOAD_MODULES"] = "qtreload,qtreload,does_not_exist"
    widget = install_hot_reload(None)
    assert widget is not None
    assert widget._modules == ["qtreload"]

    os.environ["QTRELOAD_HOT_RELOAD"] = "0"
    assert install_hot_reload(None) is None


def _make_widget(qtbot, modules, messages=None):
    from qtreload.qt_reload import QtReloadWidget

    widget = QtReloadWidget(modules, log_func=messages.append if messages is not None else None)
    qtbot.addWidget(widget)
    widget._reload_timer.setInterval(10)
    return widget


def test_reload_batches_multiple_files(qtbot, make_package):
    """Test saving several files at once reloads all of them (previously only the last one)."""
    import importlib

    name, root = make_package({"a.py": "def value():\n    return 1\n", "b.py": "def value():\n    return 1\n"})
    mod_a = importlib.import_module(f"{name}.a")
    mod_b = importlib.import_module(f"{name}.b")
    widget = _make_widget(qtbot, [name])

    emitted = []
    widget.evt_pyfile.connect(emitted.append)
    for filename in ("a.py", "b.py"):
        (root / filename).write_text("def value():\n    return 2\n")
        widget.on_reload_file(str(root / filename))

    qtbot.waitUntil(lambda: len(emitted) == 2, timeout=2000)
    assert sorted(emitted) == [f"{name}.a", f"{name}.b"]
    assert mod_a.value() == 2
    assert mod_b.value() == 2


def test_reload_readds_replaced_file(qtbot, make_package):
    """Test files dropped by the watcher (atomic save) are watched again after reload."""
    import importlib

    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    widget = _make_widget(qtbot, [name])
    path = str(root / "a.py")
    assert path in widget._watcher.files()

    widget._watcher.removePath(path)
    with qtbot.waitSignal(widget.evt_pyfile, timeout=2000):
        widget.on_reload_file(path)
    assert path in widget._watcher.files()


def test_reload_subpackage_module_name(qtbot, make_package):
    """Test watching a subpackage reloads modules under their full name."""
    import importlib

    name, root = make_package({"sub/__init__.py": "", "sub/mod.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.sub.mod")
    widget = _make_widget(qtbot, [f"{name}.sub"])
    path = str(root / "sub" / "mod.py")
    assert widget.get_module_for_path(path) == f"{name}.sub.mod"

    (root / "sub" / "mod.py").write_text("def value():\n    return 2\n")
    with qtbot.waitSignal(widget.evt_pyfile, timeout=2000) as blocker:
        widget.on_reload_file(path)
    assert blocker.args == [f"{name}.sub.mod"]
    assert mod.value() == 2


def test_reload_skips_unimported_module(qtbot, make_package):
    """Test files of modules that were never imported are not imported by the reloader."""
    import sys

    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    messages = []
    widget = _make_widget(qtbot, [name], messages)

    widget.on_reload_file(str(root / "a.py"))
    qtbot.waitUntil(lambda: any("has not been imported" in msg for msg in messages), timeout=2000)
    assert f"{name}.a" not in sys.modules


def test_reload_reports_syntax_error(qtbot, make_package):
    """Test errors raised while executing the new code are shown and no signal is emitted."""
    import importlib

    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.a")
    messages = []
    widget = _make_widget(qtbot, [name], messages)
    emitted = []
    widget.evt_pyfile.connect(emitted.append)

    (root / "a.py").write_text("def value(:\n")
    widget.on_reload_file(str(root / "a.py"))
    qtbot.waitUntil(lambda: any("SyntaxError" in msg for msg in messages), timeout=2000)
    assert emitted == []
    assert mod.value() == 1


def test_start_empty_then_add_module(qtbot, make_package):
    """Test the watcher is connected even when the widget starts without modules."""
    name, _ = make_package({"a.py": ""})
    widget = _make_widget(qtbot, [])
    assert widget._watcher_connected

    widget._add_module_text.setText(name)
    widget._add_module_text.editingFinished.emit()
    assert widget._modules == [], "Losing focus should not add the module"
    widget._add_module_text.returnPressed.emit()
    assert widget._modules == [name]
    assert widget._watcher.files()

    widget.setup_paths()
    assert widget._watcher_connected


def test_missing_dotted_module_does_not_raise(qtbot):
    """Test unknown dotted module names are logged instead of raising."""
    messages = []
    widget = _make_widget(qtbot, ["not_a_module_qtreload.sub"], messages)
    assert widget._modules == []
    assert any("Could not find path" in msg for msg in messages)
