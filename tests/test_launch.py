import json
import os
import subprocess
import sys

import pytest
from qtpy.QtCore import Qt, QTimer
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication, QLabel

from qtreload import launch
from qtreload.config import ReloadConfig
from qtreload.launch import DevToolsShortcut, _ExecHook, _split_argv, get_dev_tools, install_dev_tools, main

APP_SOURCE = """
import json
import sys

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QApplication

from qtreload.launch import get_dev_tools

app = QApplication.instance() or QApplication([])


def record():
    # record while the event loop runs - since Qt 6, quitting closes all windows
    tools = get_dev_tools()
    with open(sys.argv[-1], "w") as handle:
        json.dump(
            {
                "name": __name__,
                "argv": sys.argv,
                "modules": list(tools.reloader.modules) if tools is not None else None,
                "visible": tools.isVisible() if tools is not None else None,
            },
            handle,
        )
    app.quit()


QTimer.singleShot(0, record)
app.exec()
"""


@pytest.fixture(autouse=True)
def reset_dev_tools(monkeypatch):
    yield
    tools = launch._dev_tools
    if tools is not None:
        tools.close()
        tools.deleteLater()
    launch._dev_tools = None


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["app.py"], ([], "app.py", None, [])),
        (["-w", "a,b", "--show", "app.py", "--flag", "x"], (["-w", "a,b", "--show"], "app.py", None, ["--flag", "x"])),
        (["--watch", "a", "-m", "pkg.main", "-v"], (["--watch", "a"], None, "pkg.main", ["-v"])),
        (["--shortcut", "F5", "-m", "pkg"], (["--shortcut", "F5"], None, "pkg", [])),
        (["--show"], (["--show"], None, None, [])),
    ],
)
def test_split_argv(argv, expected):
    assert _split_argv(argv) == expected


def test_split_argv_missing_module():
    with pytest.raises(SystemExit):
        _split_argv(["-m"])


def test_main_requires_target(capsys):
    with pytest.raises(SystemExit):
        main(["--show"])
    assert "specify the script or the module" in capsys.readouterr().err


def test_shortcut_toggles_widget(qtbot):
    tools, other = QLabel("tools"), QLabel("other")
    qtbot.addWidget(tools)
    qtbot.addWidget(other)
    other.show()
    shortcut = DevToolsShortcut(tools, "Ctrl+Shift+F12")
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier

    QTest.keyClick(other, Qt.Key.Key_F12, modifiers)
    assert tools.isVisible()
    QTest.keyClick(other, Qt.Key.Key_F12, modifiers)
    assert not tools.isVisible()
    QTest.keyClick(other, Qt.Key.Key_F12)
    assert not tools.isVisible(), "Other key sequences are ignored"
    assert shortcut.parent() is tools


def test_install_dev_tools(qtbot, make_package):
    name, _ = make_package({"a.py": ""})
    tools = install_dev_tools(ReloadConfig(modules=(name,)), shortcut="F9")
    assert get_dev_tools() is tools
    assert install_dev_tools() is tools, "Installed only once"
    assert tools.reloader.modules == (name,)
    assert not tools.isVisible()
    assert not tools.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose)
    assert tools.shortcut.sequence.toString() == "F9"
    assert any("Press F9" in msg for msg, _ in tools.reloader.messages)


def test_install_dev_tools_show_and_warning(qtbot):
    tools = install_dev_tools(ReloadConfig(), show=True)
    assert tools.isVisible()
    assert any("No modules are watched" in msg for msg, _ in tools.reloader.messages)


def test_exec_hook_runs_once_and_restores(qtbot):
    calls = []
    original = QApplication.__dict__.get("exec")
    hook = _ExecHook(lambda: calls.append(True))
    app = QApplication.instance()

    hook.patch()
    assert QApplication.__dict__.get("exec") is not original
    QTimer.singleShot(0, app.quit)
    assert app.exec() == 0
    assert calls == [True]
    assert QApplication.__dict__.get("exec") is original

    hook.patch()
    QTimer.singleShot(0, app.quit)
    QApplication.exec()
    assert calls == [True, True]
    assert QApplication.__dict__.get("exec") is original


def test_exec_hook_survives_failing_install(qtbot):
    def fail():
        raise ValueError("broken")

    hook = _ExecHook(fail)
    hook.patch()
    app = QApplication.instance()
    QTimer.singleShot(0, app.quit)
    assert app.exec() == 0


def test_main_runs_script(qtbot, make_package, tmp_path):
    name, _ = make_package({"a.py": ""})
    script = tmp_path / "app.py"
    script.write_text(APP_SOURCE)
    output = tmp_path / "out.json"
    argv_before = sys.argv[:]
    exec_before = QApplication.__dict__.get("exec")

    assert main(["--watch", name, "--show", str(script), "--flag", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result == {
        "name": "__main__",
        "argv": [str(script), "--flag", str(output)],
        "modules": [name],
        "visible": True,
    }
    assert sys.argv == argv_before
    assert QApplication.__dict__.get("exec") is exec_before, "QApplication.exec is restored"


def test_main_runs_module_and_watches_its_package(qtbot, make_package, tmp_path):
    name, _ = make_package({"main.py": APP_SOURCE})
    output = tmp_path / "out.json"

    assert main(["-m", f"{name}.main", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["name"] == "__main__"
    assert result["modules"] == [name]
    assert result["argv"][1:] == [str(output)]


def test_command_line_end_to_end(make_package, tmp_path):
    """Test `python -m qtreload` in a separate process."""
    name, root = make_package({"a.py": ""})
    script = tmp_path / "app.py"
    script.write_text(APP_SOURCE)
    output = tmp_path / "out.json"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(root.parent)}

    completed = subprocess.run(
        [sys.executable, "-m", "qtreload", "-w", name, str(script), str(output)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text())
    assert result["modules"] == [name]
    assert result["visible"] is False
