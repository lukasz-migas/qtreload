import logging
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
    for path in widget.path_to_index_map:
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
    assert widget.reloader.modules == ("qtreload",)

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map:
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"
        paths = widget.reloader._get_file_paths(module)
        assert len(paths) > 0, "Expected more than 1 path"

    os.environ["QTRELOAD_HOT_RELOAD_MODULES"] = "qtreload,qtreload,does_not_exist"
    widget = install_hot_reload(None)
    assert widget is not None
    assert widget.reloader.modules == ("qtreload",)

    os.environ["QTRELOAD_HOT_RELOAD"] = "0"
    assert install_hot_reload(None) is None


def _make_widget(qtbot, modules, messages=None):
    from qtreload.qt_reload import QtReloadWidget

    widget = QtReloadWidget(modules, log_func=messages.append if messages is not None else None)
    qtbot.addWidget(widget)
    widget.reloader._reload_timer.setInterval(10)
    return widget


def _list_texts(list_widget):
    return [list_widget.item(row).text() for row in range(list_widget.count())]


def test_widget_forwards_reloader_signals(qtbot, make_package):
    """Test the widget re-emits the reloader signals and shows its log messages."""
    import importlib

    name, root = make_package({"a.py": "def value():\n    return 1\n", "style.qss": ""})
    importlib.import_module(f"{name}.a")
    messages = []
    widget = _make_widget(qtbot, [name], messages)

    (root / "a.py").write_text("def value():\n    return 2\n")
    with qtbot.waitSignal(widget.evt_pyfile, timeout=2000) as blocker:
        widget.on_reload_file(str(root / "a.py"))
    assert blocker.args == [f"{name}.a"]

    with qtbot.waitSignal(widget.evt_stylesheet, timeout=2000):
        widget.on_reload_file(str(root / "style.qss"))
    assert messages
    assert messages[-1] in widget._log_edit.toPlainText()


def test_widget_shows_reloader_state(qtbot, make_package):
    """Test the module and file lists follow changes made through the reloader."""
    name, root = make_package({"a.py": "", "b.py": ""})
    widget = _make_widget(qtbot, [])
    assert _list_texts(widget._modules_list) == []

    widget.reloader.add_module(name)
    assert _list_texts(widget._modules_list) == [name]
    assert _list_texts(widget._files_list) == [str(root / "a.py"), str(root / "b.py")]

    widget.reloader.set_patterns(py_pattern=("a.py",))
    assert widget._py_pattern_text.text() == "a.py"
    assert _list_texts(widget._files_list) == [str(root / "a.py")]


def test_widget_pattern_fields(qtbot, make_package):
    """Test editing pattern fields updates the reloader."""
    name, root = make_package({"a.py": "", "b.py": "", "style.qss": ""})
    widget = _make_widget(qtbot, [name])

    widget._py_pattern_text.setText(" b.py , ")
    widget.on_py_pattern_changed()
    assert widget.reloader.py_pattern == ("b.py",)
    assert widget.py_pattern == ("b.py",)
    widget._stylesheet_pattern_text.setText("")
    widget.on_stylesheet_pattern_changed()
    assert widget.reloader.files == [str(root / "b.py")]


def test_widget_remove_selected_module(qtbot, make_package):
    """Test removing modules selected in the list."""
    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    widget = _make_widget(qtbot, [name_a, name_b])

    widget.on_remove_module()
    assert widget.reloader.modules == (name_a, name_b), "Nothing selected - nothing removed"
    widget._modules_list.item(0).setSelected(True)
    widget.on_remove_module()
    assert widget.reloader.modules == (name_b,)
    assert _list_texts(widget._modules_list) == [name_b]


def test_widget_add_module_on_return_only(qtbot, make_package):
    """Test the module is added on Enter, not when the text field loses focus."""
    name, _ = make_package({"a.py": ""})
    widget = _make_widget(qtbot, [])

    widget._add_module_text.setText(name)
    widget._add_module_text.editingFinished.emit()
    assert widget.reloader.modules == (), "Losing focus should not add the module"
    widget._add_module_text.returnPressed.emit()
    assert widget.reloader.modules == (name,)
    assert widget._add_module_text.text() == ""


def test_widget_status_and_colored_log(qtbot, make_package):
    """Test the status line shows the last reload and errors are colored in the log."""
    import importlib

    from qtreload.qt_reload import LEVEL_COLORS, SUCCESS_COLOR

    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    messages = []
    widget = _make_widget(qtbot, [name], messages)
    assert "Watching for" in widget._log_edit.toPlainText(), "Setup messages should be shown"
    assert widget._status_label.text() == "No reloads yet"

    (root / "a.py").write_text("def value():\n    return 2\n")
    widget.reloader.reload_path(str(root / "a.py"))
    assert widget._status_label.text() == f"Reloaded '{name}.a': updated value"
    assert SUCCESS_COLOR in widget._status_label.styleSheet()

    (root / "a.py").write_text("def value(:\n")
    widget.reloader.reload_path(str(root / "a.py"))
    assert widget._status_label.text().startswith(f"Failed to reload '{name}.a': SyntaxError")
    assert "Traceback" in widget._status_label.toolTip()
    assert LEVEL_COLORS[logging.ERROR] in widget._log_edit.toHtml()

    widget.log_message("<class 'int'> & more")
    assert "<class 'int'> & more" in widget._log_edit.toPlainText()
    assert any("<class 'int'>" in msg for msg in messages), "log_func should receive messages"

    collected = []
    widget.log_func = collected.append
    widget.log_message("after")
    assert collected and collected[0].endswith("after")
