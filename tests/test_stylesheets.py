import logging
import sys
import pytest
from qtpy.QtWidgets import QApplication, QWidget

from qtreload.utilities import render_stylesheet


@pytest.fixture
def widget(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


def test_render_stylesheet():
    text = "QWidget { color: {{ color }}; background: {{background}}; border: {{ missing }}; }"
    rendered, missing = render_stylesheet(text, {"color": "red", "background": 1})
    assert rendered == "QWidget { color: red; background: 1; border: {{ missing }}; }"
    assert missing == {"missing"}
    assert render_stylesheet("{ }", {}) == ("{ }", set())


def test_register_applies_immediately(make_reloader, widget, tmp_path):
    path = tmp_path / "style.qss"
    path.write_text("QWidget { color: red; }")
    reloader = make_reloader()

    reloader.register_stylesheet(path, widget)
    assert widget.styleSheet() == "QWidget { color: red; }"
    assert reloader.stylesheets == [str(path.resolve())]
    assert str(path.resolve()) in reloader.files
    assert str(path.resolve()) in reloader._watcher.files()

    with pytest.raises(FileNotFoundError):
        reloader.register_stylesheet(tmp_path / "missing.qss", widget)


def test_register_applies_to_application_by_default(make_reloader, qapp, tmp_path):
    path = tmp_path / "style.qss"
    path.write_text("QLabel { color: blue; }")
    reloader = make_reloader()
    previous = qapp.styleSheet()
    try:
        reloader.register_stylesheet(path)
        assert QApplication.instance().styleSheet() == "QLabel { color: blue; }"
    finally:
        reloader.unregister_stylesheet(path)
        qapp.setStyleSheet(previous)


def test_changed_stylesheet_is_reapplied(qtbot, make_reloader, widget, tmp_path):
    path = tmp_path / "style.css"
    path.write_text("QWidget { color: red; }")
    reloader = make_reloader()
    reloader.register_stylesheet(path, widget)
    changed, any_changed = [], []
    reloader.evt_stylesheet_changed.connect(changed.append)
    reloader.evt_stylesheet.connect(lambda: any_changed.append(True))

    path.write_text("QWidget { color: green; }")
    reloader.on_reload_file(str(path.resolve()))
    qtbot.waitUntil(lambda: widget.styleSheet() == "QWidget { color: green; }", timeout=2000)
    assert changed == [str(path.resolve())]
    assert any_changed == [True]


def test_stylesheets_for_same_target_are_joined(qtbot, make_reloader, widget, tmp_path):
    base, extra, other = tmp_path / "base.qss", tmp_path / "extra.qss", tmp_path / "other.qss"
    base.write_text("A")
    extra.write_text("B")
    other.write_text("C")
    other_widget = QWidget()
    qtbot.addWidget(other_widget)
    reloader = make_reloader()

    reloader.register_stylesheet(base, widget)
    reloader.register_stylesheet(extra, widget)
    reloader.register_stylesheet(other, other_widget)
    assert widget.styleSheet() == "A\nB"
    assert other_widget.styleSheet() == "C"

    extra.write_text("B2")
    reloader.reload_path(str(extra.resolve()))
    assert widget.styleSheet() == "A\nB2"
    assert other_widget.styleSheet() == "C"

    reloader.register_stylesheet(base, widget)
    assert reloader.stylesheets == [str(p.resolve()) for p in (base, extra, other)], "No duplicate registration"


def test_stylesheet_variables(make_reloader, widget, tmp_path):
    path = tmp_path / "style.qss"
    path.write_text("QWidget { color: {{ text }}; border: {{ unknown }}; }")
    theme = {"text": "black"}
    messages = []
    reloader = make_reloader(messages=messages)

    reloader.register_stylesheet(path, widget, variables=lambda: theme)
    assert widget.styleSheet() == "QWidget { color: black; border: {{ unknown }}; }"
    assert any("unknown variables: unknown" in msg for msg in messages)
    assert any(level == logging.WARNING and "unknown" in msg for msg, level in reloader.messages)

    theme["text"] = "white"
    reloader.apply_stylesheets()
    assert widget.styleSheet() == "QWidget { color: white; border: {{ unknown }}; }"

    reloader.register_stylesheet(path, widget, variables={"text": "red", "unknown": "none"})
    assert widget.styleSheet() == "QWidget { color: red; border: none; }"


def test_registered_stylesheet_survives_refresh_and_unregister(make_reloader, make_package, widget, tmp_path):
    name, _ = make_package({"a.py": ""})
    path = tmp_path / "style.qss"
    path.write_text("A")
    reloader = make_reloader([name])
    reloader.register_stylesheet(path, widget)

    reloader.refresh()
    assert str(path.resolve()) in reloader._watcher.files()

    reloader.unregister_stylesheet(path, widget)
    assert reloader.stylesheets == []
    assert str(path.resolve()) not in reloader._watcher.files()
    assert widget.styleSheet() == "A", "Unregistering keeps the current stylesheet"


def test_module_stylesheet_registered_and_unregistered(make_reloader, make_package, widget):
    name, root = make_package({"theme.qss": "A"})
    reloader = make_reloader([name])
    path = root / "theme.qss"
    reloader.register_stylesheet(path, widget)
    reloader.unregister_stylesheet(path)
    assert str(path) in reloader._watcher.files(), "Still watched as part of the module"
    assert reloader.files == [str(path)]


def test_deleted_target_is_dropped(qtbot, make_reloader, tmp_path):
    path = tmp_path / "style.qss"
    path.write_text("A")
    reloader = make_reloader()
    widget = QWidget()
    reloader.register_stylesheet(path, widget)
    assert reloader.stylesheets

    del widget
    reloader.apply_stylesheets()
    assert reloader.stylesheets == []


def test_unreadable_stylesheet_keeps_current(qtbot, make_reloader, widget, tmp_path):
    path = tmp_path / "style.qss"
    path.write_text("A")
    messages = []
    reloader = make_reloader(messages=messages)
    reloader.register_stylesheet(path, widget)

    path.unlink()
    reloader.apply_stylesheets()
    assert widget.styleSheet() == "A"
    assert any("Could not read stylesheet" in msg for msg in messages)


def test_widget_forwards_stylesheet_changed(qtbot, tmp_path):
    from qtreload.qt_reload import QtReloadWidget

    path = tmp_path / "style.qss"
    path.write_text("A")
    reload_widget = QtReloadWidget([])
    qtbot.addWidget(reload_widget)
    target = QWidget()
    qtbot.addWidget(target)
    reload_widget.reloader.register_stylesheet(path, target)
    assert str(path.resolve()) in [
        reload_widget._files_list.item(i).text() for i in range(reload_widget._files_list.count())
    ]

    with qtbot.waitSignal(reload_widget.evt_stylesheet_changed) as blocker:
        reload_widget.reloader.reload_path(str(path.resolve()))
    assert blocker.args == [str(path.resolve())]


@pytest.mark.xfail(sys.platform == "win32", reason="Occasionally there is a timeout exception.")
def test_registered_stylesheet_file_system_events(qtbot, make_reloader, widget, tmp_path):
    """Test real watcher events for a stylesheet outside any module, including a replace-style save."""
    import os

    path = tmp_path / "style.qss"
    path.write_text("A")
    reloader = make_reloader()
    reloader.register_stylesheet(path, widget)

    for value in ("B", "C"):
        tmp = tmp_path / f".style.{value}.tmp"
        tmp.write_text(value)
        os.replace(tmp, path)
        qtbot.waitUntil(lambda value=value: widget.styleSheet() == value, timeout=5000)
