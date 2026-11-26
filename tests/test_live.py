import importlib

import pytest
from qtpy.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qtreload.live import is_alive, replace_widget


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_replace_in_nested_layout(host):
    outer = QVBoxLayout(host)
    inner = QHBoxLayout()
    outer.addLayout(inner)
    before, old, after = QLabel("before"), QLabel("old"), QLabel("after")
    for label in (before, old, after):
        inner.addWidget(label)

    new = QLabel("new")
    replace_widget(old, new)
    assert [inner.itemAt(i).widget() for i in range(inner.count())] == [before, new, after]
    assert new.isVisible()
    assert old.isHidden()


def test_replace_keeps_hidden_state(host):
    layout = QVBoxLayout(host)
    old = QLabel("old")
    layout.addWidget(old)
    old.hide()

    new = QLabel("new")
    replace_widget(old, new)
    assert new.isHidden()


def test_replace_in_splitter(host):
    splitter = QSplitter(host)
    first, old = QLabel("first"), QLabel("old")
    splitter.addWidget(first)
    splitter.addWidget(old)

    new = QLabel("new")
    replace_widget(old, new)
    assert splitter.widget(1) is new
    assert splitter.count() == 2


def test_replace_in_tab_widget(host):
    tabs = QTabWidget(host)
    first, old = QLabel("first"), QLabel("old")
    tabs.addTab(first, "First")
    tabs.addTab(old, "Old")
    tabs.setTabToolTip(1, "tip")
    tabs.setCurrentIndex(1)

    new = QLabel("new")
    replace_widget(old, new)
    assert tabs.widget(1) is new
    assert tabs.tabText(1) == "Old"
    assert tabs.tabToolTip(1) == "tip"
    assert tabs.currentIndex() == 1
    assert tabs.count() == 2


def test_replace_in_stacked_widget(host):
    stack = QStackedWidget(host)
    first, old = QLabel("first"), QLabel("old")
    stack.addWidget(first)
    stack.addWidget(old)
    stack.setCurrentWidget(old)

    new = QLabel("new")
    replace_widget(old, new)
    assert stack.widget(1) is new
    assert stack.currentWidget() is new


def test_replace_in_dock_scroll_and_main_window(qtbot):
    window = QMainWindow()
    qtbot.addWidget(window)
    old_central = QLabel("central")
    window.setCentralWidget(old_central)
    dock = QDockWidget("Dock", window)
    old_dock = QLabel("dock")
    dock.setWidget(old_dock)
    scroll = QScrollArea()
    old_scroll = QLabel("scroll")
    scroll.setWidget(old_scroll)
    dock2 = QDockWidget("Scroll", window)
    dock2.setWidget(scroll)
    window.show()

    new_central, new_dock, new_scroll = QLabel("c"), QLabel("d"), QLabel("s")
    replace_widget(old_central, new_central)
    replace_widget(old_dock, new_dock)
    replace_widget(old_scroll, new_scroll)
    assert window.centralWidget() is new_central
    assert dock.widget() is new_dock
    assert scroll.widget() is new_scroll


def test_replace_top_level_window(qtbot):
    old = QLabel("old")
    qtbot.addWidget(old)
    old.setGeometry(100, 120, 300, 200)
    old.show()

    new = QLabel("new")
    qtbot.addWidget(new)
    replace_widget(old, new)
    assert new.isVisible()
    assert not old.isVisible()
    assert new.geometry().size() == old.geometry().size()


def test_replace_without_layout(host):
    old = QLabel("old", host)
    old.setGeometry(5, 6, 70, 20)

    new = QLabel("new")
    replace_widget(old, new)
    assert new.parentWidget() is host
    assert new.geometry() == old.geometry()


def test_is_alive(qtbot):
    widget = QLabel()
    assert is_alive(widget)
    widget.deleteLater()
    qtbot.wait(10)
    assert not is_alive(widget)


PANEL_SOURCE = """
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget


class Panel(QWidget):
    def __init__(self, title="panel"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
"""


@pytest.fixture
def panel_package(make_package):
    name, root = make_package({"panel.py": PANEL_SOURCE, "other.py": "def value():\n    return 1\n"})
    module = importlib.import_module(f"{name}.panel")
    importlib.import_module(f"{name}.other")
    return name, root, module


def _labels(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def _add_button(root):
    source = PANEL_SOURCE + "        layout.addWidget(QLabel('new button'))\n"
    (root / "panel.py").write_text(source)


def test_rebuild_on_reload(qtbot, make_reloader, panel_package, host):
    name, root, module = panel_package
    reloader = make_reloader([name])
    live = reloader.register_factory(lambda: module.Panel("hello"))
    assert live in reloader.live_widgets
    assert live.modules[0] == f"{name}.panel"
    layout = QVBoxLayout(host)
    layout.addWidget(live.widget)
    old = live.widget

    _add_button(root)
    with qtbot.waitSignal(live.evt_rebuilt) as blocker:
        reloader.reload_path(str(root / "panel.py"))
    assert blocker.args == [live.widget]
    assert live.widget is not old
    assert layout.itemAt(0).widget() is live.widget
    assert _labels(live.widget) == ["hello", "new button"]
    assert any("Rebuilt 'Panel'" in msg for msg, _ in reloader.messages)


def test_rebuild_once_per_batch(qtbot, make_reloader, make_package):
    name, root = make_package({"panel.py": PANEL_SOURCE, "helpers.py": "def value():\n    return 1\n"})
    module = importlib.import_module(f"{name}.panel")
    importlib.import_module(f"{name}.helpers")
    reloader = make_reloader([name])
    live = reloader.register_factory(module.Panel, modules=[name])
    rebuilt = []
    live.evt_rebuilt.connect(rebuilt.append)

    _add_button(root)
    (root / "helpers.py").write_text("def value():\n    return 2\n")
    reloader.on_reload_file(str(root / "panel.py"))
    reloader.on_reload_file(str(root / "helpers.py"))
    qtbot.waitUntil(lambda: len(rebuilt) == 1, timeout=2000)
    qtbot.wait(50)
    assert len(rebuilt) == 1


def test_no_rebuild_for_unrelated_unchanged_or_failed(qtbot, make_reloader, panel_package):
    name, root, module = panel_package
    messages = []
    reloader = make_reloader([name], messages)
    live = reloader.register_factory(module.Panel)
    rebuilt = []
    live.evt_rebuilt.connect(rebuilt.append)

    (root / "other.py").write_text("def value():\n    return 2\n")
    reloader.reload_path(str(root / "other.py"))
    reloader.reload_path(str(root / "panel.py"))  # unchanged
    (root / "panel.py").write_text("class Panel(:\n")
    reloader.reload_path(str(root / "panel.py"))
    assert rebuilt == []
    assert any("Not rebuilding 'Panel'" in msg and "failed to reload" in msg for msg in messages)


def test_existing_widget_and_state_transfer(qtbot, make_reloader, panel_package):
    name, root, module = panel_package
    reloader = make_reloader([name])
    first = module.Panel("first")
    qtbot.addWidget(first)
    live = None

    def factory():
        # the old instance is still available while the factory runs
        title = _labels(live.widget)[0] + " again" if live is not None else "unused"
        return module.Panel(title)

    live = reloader.register_factory(factory, widget=first)
    assert live.widget is first

    _add_button(root)
    reloader.reload_path(str(root / "panel.py"))
    assert _labels(live.widget) == ["first again", "new button"]


def test_failing_factory_keeps_widget(qtbot, make_reloader, panel_package):
    name, root, module = panel_package
    messages = []
    reloader = make_reloader([name], messages)
    calls = []

    def factory():
        calls.append(True)
        if len(calls) > 1:
            raise ValueError("broken")
        return module.Panel()

    live = reloader.register_factory(factory, modules=[name])
    old = live.widget
    qtbot.addWidget(old)
    _add_button(root)
    reloader.reload_path(str(root / "panel.py"))
    assert live.widget is old
    assert any("Failed to rebuild 'Panel'" in msg and "ValueError: broken" in msg for msg in messages)


def test_deleted_widget_is_not_rebuilt(qtbot, make_reloader, panel_package):
    name, root, module = panel_package
    reloader = make_reloader([name])
    live = reloader.register_factory(module.Panel)
    live.widget.deleteLater()
    qtbot.wait(10)

    _add_button(root)
    reloader.reload_path(str(root / "panel.py"))
    assert not is_alive(live.widget)


def test_unregister_factory(qtbot, make_reloader, panel_package):
    name, root, module = panel_package
    reloader = make_reloader([name])
    live = reloader.register_factory(module.Panel)
    qtbot.addWidget(live.widget)
    old = live.widget
    live.unregister()
    assert reloader.live_widgets == []

    _add_button(root)
    reloader.reload_path(str(root / "panel.py"))
    assert live.widget is old


def test_matches_module_prefixes(make_reloader, panel_package):
    name, _, module = panel_package
    reloader = make_reloader([name])
    live = reloader.register_factory(module.Panel, modules=["pkg.panels"])
    assert live.matches("pkg.panels")
    assert live.matches("pkg.panels.sub")
    assert not live.matches("pkg.panels_other")
    assert live.matches(f"{name}.panel")
