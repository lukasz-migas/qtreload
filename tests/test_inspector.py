import json
import sys
from pathlib import Path

import pytest
from qtpy.QtCore import QPoint, Qt
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from qtreload import inspector as inspector_module
from qtreload.inspector import HighlightOverlay, WidgetInspector, describe_widget, find_source, open_in_editor


class CustomLabel(QLabel):
    """Python subclass, so it has a source file."""


@pytest.fixture
def window(qtbot):
    window = QWidget()
    window.setObjectName("window")
    layout = QVBoxLayout(window)
    label = CustomLabel("label", window)
    label.setObjectName("custom")
    label.setStyleSheet("color: red;")
    button = QPushButton("button", window)
    layout.addWidget(label)
    layout.addWidget(button)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window, label, button


def test_find_source():
    path, line = find_source(CustomLabel)
    assert path == __file__
    assert "class CustomLabel" in Path(path).read_text().splitlines()[line - 1]
    assert find_source(QLabel) is None


def test_describe_widget(window):
    _, label, button = window
    info = describe_widget(label)
    assert info.class_name == "CustomLabel"
    assert info.module == __name__
    assert info.source_file == __file__
    assert info.object_name == "custom"
    assert info.parents == ("QWidget",)
    assert info.stylesheet == "color: red;"
    assert info.visible
    assert info.geometry[2:] == (label.width(), label.height())
    text = info.format()
    assert "Class:       CustomLabel" in text
    assert f"Source:      {__file__}:" in text

    assert describe_widget(button).source_file is None


@pytest.fixture
def recorder(tmp_path):
    """Command template of a fake editor that writes its arguments to a file."""
    script = tmp_path / "editor.py"
    output = tmp_path / "args.json"
    script.write_text(f"import json, sys\nopen({str(output)!r}, 'w').write(json.dumps(sys.argv[1:]))\n")
    return f'"{sys.executable}" "{script}" --line {{line}} {{path}}', output


def test_open_in_editor_with_command(qtbot, recorder, tmp_path, monkeypatch):
    command, output = recorder
    target = tmp_path / "module.py"
    assert open_in_editor(target, 12, command)
    qtbot.waitUntil(output.exists, timeout=5000)
    assert json.loads(output.read_text()) == ["--line", "12", str(target)]

    output.unlink()
    monkeypatch.setenv("QTRELOAD_EDITOR", command)
    assert open_in_editor(target)
    qtbot.waitUntil(output.exists, timeout=5000)
    assert json.loads(output.read_text()) == ["--line", "1", str(target)]


def test_open_in_editor_errors_and_default(tmp_path, monkeypatch):
    monkeypatch.delenv("QTRELOAD_EDITOR", raising=False)
    assert not open_in_editor(tmp_path / "a.py", command="not-an-editor-qtreload {path}")
    assert not open_in_editor(tmp_path / "a.py", command="editor {unknown}")

    opened = []
    monkeypatch.setattr(inspector_module.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    assert open_in_editor(tmp_path / "a.py", 3)
    assert Path(opened[0].toLocalFile()) == tmp_path / "a.py"


def test_highlight_overlay(window):
    top, label, _ = window
    overlay = HighlightOverlay()
    overlay.highlight(label)
    assert overlay.parentWidget() is top
    assert overlay.isVisible()
    assert overlay.geometry().topLeft() == label.mapTo(top, QPoint(0, 0))
    assert overlay.size() == label.size()
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert overlay.target is label

    overlay.highlight(None)
    assert not overlay.isVisible()
    assert overlay.target is None


def test_inspector_hover_and_exclude(qtbot, window):
    _, label, button = window
    inspector = WidgetInspector(exclude=button)
    hovered = []
    inspector.evt_hovered.connect(hovered.append)

    inspector.hover(label)
    inspector.hover(label)
    inspector.hover(button)
    assert hovered == [label]
    assert inspector.overlay.target is None, "Excluded widgets are not highlighted"
    inspector.hover(inspector.overlay)
    assert hovered == [label]


def test_inspector_polls_widget_under_cursor(qtbot, window, monkeypatch):
    _, label, _ = window
    inspector = WidgetInspector()
    monkeypatch.setattr(inspector_module.QApplication, "widgetAt", staticmethod(lambda pos: label))
    with qtbot.waitSignal(inspector.evt_hovered) as blocker:
        inspector._poll()
    assert blocker.args == [label]


def test_inspector_click_selects_without_clicking(qtbot, window):
    _, _, button = window
    inspector = WidgetInspector()
    clicked, selected, active = [], [], []
    button.clicked.connect(lambda: clicked.append(True))
    inspector.evt_selected.connect(selected.append)
    inspector.evt_active_changed.connect(active.append)

    inspector.start()
    assert inspector.active
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert selected == [button]
    assert clicked == []
    assert not inspector.active
    assert active == [True, False]
    assert inspector.overlay.target is button

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert clicked == [True], "Clicks work again after picking"


def test_inspector_escape_cancels(qtbot, window):
    _, label, _ = window
    inspector = WidgetInspector()
    inspector.start()
    inspector.hover(label)
    QTest.keyClick(label, Qt.Key.Key_Escape)
    assert not inspector.active
    assert inspector.overlay.target is None


def test_overlay_recreated_after_window_deleted(qtbot):
    window = QWidget()
    child = QLabel("x", window)
    window.show()
    inspector = WidgetInspector()
    inspector.hover(child)
    old_overlay = inspector.overlay
    window.deleteLater()
    qtbot.wait(10)
    assert inspector.overlay is not old_overlay
    QApplication.processEvents()


def test_reload_widget_inspector_tab(qtbot, window, monkeypatch):
    from qtreload import qt_reload
    from qtreload.qt_reload import QtReloadWidget

    _, label, button = window
    opened = []
    monkeypatch.setattr(
        qt_reload, "open_in_editor", lambda path, line, command: opened.append((path, line, command)) or True
    )
    widget = QtReloadWidget([], editor="my-editor {path}")
    qtbot.addWidget(widget)
    assert not widget._open_source_btn.isEnabled()

    widget.inspect_widget(label)
    assert widget.selected_widget is label
    assert "CustomLabel" in widget._widget_info.toPlainText()
    assert widget._open_source_btn.isEnabled()
    widget._open_source_btn.click()
    assert opened == [(__file__, find_source(CustomLabel)[1], "my-editor {path}")]

    widget.inspect_widget(button)
    assert not widget._open_source_btn.isEnabled()
    widget._parent_btn.click()
    assert widget.selected_widget is label.parentWidget()

    widget._pick_btn.click()
    assert widget.inspector.active
    widget.inspector.hover(widget._pick_btn)
    assert widget.inspector.overlay.target is not widget._pick_btn, "The reload widget itself cannot be picked"
    widget.inspector.stop()
    assert not widget._pick_btn.isChecked()

    widget.open_file("/tmp/file.py", 4)
    assert opened[-1] == ("/tmp/file.py", 4, "my-editor {path}")


def test_editor_config(tmp_path):
    from qtreload.config import load_config

    (tmp_path / "pyproject.toml").write_text('[tool.qtreload]\neditor = "code -g {path}:{line}"\n')
    assert load_config(tmp_path, environ={}).editor == "code -g {path}:{line}"
    assert load_config(tmp_path, environ={"QTRELOAD_EDITOR": "vim +{line} {path}"}).editor == "vim +{line} {path}"
    assert load_config(tmp_path, environ={"QTRELOAD_EDITOR": " "}).editor is None
    (tmp_path / "pyproject.toml").write_text("[tool.qtreload]\neditor = 1\n")
    with pytest.raises(ValueError, match="must be a string"):
        load_config(tmp_path, environ={})
