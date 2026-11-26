import importlib
import sys
from pathlib import Path

import pytest


def test_reloader_discovers_files(make_reloader, make_package):
    name, root = make_package({"a.py": "", "sub/__init__.py": "", "sub/b.py": "", "style.qss": ""})
    reloader = make_reloader([name, name, "not_a_module_qtreload"])

    assert reloader.modules == (name,)
    assert reloader.files == [str(root / "a.py"), str(root / "style.qss"), str(root / "sub" / "b.py")]
    assert sorted(reloader._watcher.files()) == sorted(reloader.files)
    assert reloader.get_module_for_path(str(root / "sub" / "b.py")) == f"{name}.sub.b"
    assert reloader.get_module_path_for_path(str(root / "a.py")) == root
    with pytest.raises(ValueError):
        reloader.get_module_for_path("/not/watched.py")


def test_reloader_without_auto_connect(make_reloader, make_package):
    name, _ = make_package({"a.py": ""})
    reloader = make_reloader([name], auto_connect=False)
    assert reloader.files == []
    assert not reloader._watcher_connected

    reloader.setup_paths()
    assert reloader.files
    assert reloader._watcher_connected


def test_reloader_manage_modules(qtbot, make_reloader, make_package):
    name_a, _ = make_package({"a.py": ""})
    name_b, _ = make_package({"b.py": ""})
    messages = []
    reloader = make_reloader([], messages)
    assert reloader._watcher_connected, "Watcher should be connected even without modules"

    with qtbot.waitSignal(reloader.evt_watchlist_changed):
        assert reloader.add_module(name_a) is True
    assert reloader.add_module(name_a) is False
    assert reloader.add_module("not_a_module_qtreload.sub") is False
    assert any("Could not find path" in msg for msg in messages)
    assert reloader.add_module(name_b) is True
    assert reloader.modules == (name_a, name_b)

    reloader.remove_modules([name_a, "unknown"])
    assert reloader.modules == (name_b,)
    assert all(name_b in path for path in reloader.files)
    assert all(name_b in path for path in reloader._watcher.files())

    reloader.replace_modules([name_a, name_a])
    assert reloader.modules == (name_a,)


def test_reloader_set_patterns(make_reloader, make_package):
    name, root = make_package({"a.py": "", "test_a.py": "", "style.qss": ""})
    reloader = make_reloader([name])
    assert str(root / "test_a.py") not in reloader.files

    reloader.set_patterns(ignore_py_pattern=())
    assert str(root / "test_a.py") in reloader.files
    reloader.set_patterns(stylesheet_pattern=())
    assert str(root / "style.qss") not in reloader.files
    assert reloader.ignore_py_pattern == ()


def test_reload_batches_multiple_files(qtbot, make_reloader, make_package):
    """Test saving several files at once reloads all of them."""
    name, root = make_package({"a.py": "def value():\n    return 1\n", "b.py": "def value():\n    return 1\n"})
    mod_a = importlib.import_module(f"{name}.a")
    mod_b = importlib.import_module(f"{name}.b")
    reloader = make_reloader([name])

    emitted = []
    reloader.evt_pyfile.connect(emitted.append)
    for filename in ("a.py", "b.py"):
        (root / filename).write_text("def value():\n    return 2\n")
        reloader.on_reload_file(str(root / filename))
        reloader.on_reload_file(str(root / filename))

    qtbot.waitUntil(lambda: len(emitted) == 2, timeout=2000)
    assert emitted == [f"{name}.a", f"{name}.b"]
    assert mod_a.value() == 2
    assert mod_b.value() == 2


def test_reload_readds_replaced_file(qtbot, make_reloader, make_package):
    """Test files dropped by the watcher (atomic save) are watched again after reload."""
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    path = str(root / "a.py")

    reloader._watcher.removePath(path)
    with qtbot.waitSignal(reloader.evt_pyfile, timeout=2000):
        reloader.on_reload_file(path)
    assert path in reloader._watcher.files()


def test_reload_skips_removed_module(qtbot, make_reloader, make_package):
    """Test changes queued for a module that was removed meanwhile are dropped."""
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    emitted = []
    reloader.evt_pyfile.connect(emitted.append)

    reloader.on_reload_file(str(root / "a.py"))
    reloader.remove_modules([name])
    qtbot.wait(50)
    assert emitted == []
    assert reloader._watcher.files() == []


def test_reload_skips_unimported_module(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    messages = []
    reloader = make_reloader([name], messages)

    reloader.on_reload_file(str(root / "a.py"))
    qtbot.waitUntil(lambda: any("has not been imported" in msg for msg in messages), timeout=2000)
    assert f"{name}.a" not in sys.modules


def test_reload_reports_syntax_error(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.a")
    messages = []
    reloader = make_reloader([name], messages)
    emitted = []
    reloader.evt_pyfile.connect(emitted.append)

    (root / "a.py").write_text("def value(:\n")
    reloader.on_reload_file(str(root / "a.py"))
    qtbot.waitUntil(lambda: any("SyntaxError" in msg for msg in messages), timeout=2000)
    assert emitted == []
    assert mod.value() == 1


def test_reload_path_and_reload_all(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "def value():\n    return 1\n", "style.qss": ""})
    mod = importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])

    with qtbot.waitSignal(reloader.evt_stylesheet):
        reloader.reload_path(str(root / "style.qss"))
    with qtbot.waitSignal(reloader.evt_stylesheet):
        reloader.reload_stylesheets()

    (root / "a.py").write_text("def value():\n    return 3\n")
    with qtbot.waitSignal(reloader.evt_pyfile) as blocker:
        reloader.reload_all_py()
    assert blocker.args == [f"{name}.a"]
    assert mod.value() == 3


def test_reloader_watches_package_directories(make_reloader, make_package):
    name, root = make_package(
        {"a.py": "", "sub/__init__.py": "", "sub/b.py": "", "__pycache__/x.pyc": "", ".hidden/c.py": ""}
    )
    reloader = make_reloader([name])

    assert sorted(reloader._directory_to_index_map) == sorted([str(root), str(root / "sub")])
    assert str(root / "__pycache__") not in reloader._directory_to_index_map

    reloader.remove_modules([name])
    assert reloader._directory_to_index_map == {}


def test_reloader_does_not_watch_single_file_module_directory(make_reloader):
    reloader = make_reloader(["textwrap"])
    assert reloader.files
    assert reloader._directory_to_index_map == {}


def test_discover_new_and_deleted_files(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "", "b.py": ""})
    reloader = make_reloader([name])

    (root / "new.py").write_text("")
    (root / "style.qss").write_text("")
    (root / "b.py").unlink()
    (root / "pkg").mkdir()
    (root / "pkg" / "c.py").write_text("")
    with qtbot.waitSignal(reloader.evt_watchlist_changed, timeout=2000):
        reloader.on_directory_changed(str(root))

    expected = [str(root / "a.py"), str(root / "new.py"), str(root / "style.qss"), str(root / "pkg" / "c.py")]
    assert sorted(reloader.files) == sorted(expected)
    assert str(root / "pkg") in reloader._directory_to_index_map
    assert reloader.get_module_for_path(str(root / "pkg" / "c.py")) == f"{name}.pkg.c"


def test_discover_without_changes_does_not_emit(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": ""})
    reloader = make_reloader([name])
    emitted = []
    reloader.evt_watchlist_changed.connect(lambda: emitted.append(True))

    reloader.on_directory_changed(str(root))
    reloader.on_directory_changed("/not/watched")
    qtbot.wait(50)
    assert emitted == []


def test_discover_removed_directory(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "", "sub/b.py": ""})
    reloader = make_reloader([name])
    assert str(root / "sub" / "b.py") in reloader.files

    (root / "sub" / "b.py").unlink()
    (root / "sub").rmdir()
    with qtbot.waitSignal(reloader.evt_watchlist_changed, timeout=2000):
        reloader.on_directory_changed(str(root / "sub"))
    assert reloader.files == [str(root / "a.py")]
    assert str(root / "sub") not in reloader._directory_to_index_map


@pytest.mark.xfail(sys.platform == "win32", reason="Occasionally there is a PermissionError on Windows.")
def test_file_system_events_end_to_end(qtbot, make_reloader, make_package):
    """Test real watcher events: repeated replace-style saves reload every time and new files are discovered."""
    import os

    name, root = make_package({"a.py": "def value():\n    return 0\n"})
    mod = importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    path = root / "a.py"

    for value in (1, 2, 3):
        tmp = root / f".a.py.{value}.tmp"
        tmp.write_text(f"def value():\n    return {value}\n")
        os.replace(tmp, path)
        qtbot.waitUntil(lambda value=value: mod.value() == value, timeout=5000)

    (root / "new.py").write_text("")
    qtbot.waitUntil(lambda: str(root / "new.py") in reloader.files, timeout=5000)


def test_reload_batch_in_import_order(qtbot, make_reloader, make_package):
    """Test a module is reloaded after the module it imports, so it can use names that were just added there."""
    name, root = make_package(
        {
            "a.py": "from .b import old\n\ndef value():\n    return old()\n",
            "b.py": "def old():\n    return 1\n",
        }
    )
    mod_a = importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    emitted = []
    reloader.evt_pyfile.connect(emitted.append)

    # 'a' sorts first, but now needs a function that only exists in the new version of 'b'
    (root / "a.py").write_text("from .b import new\n\ndef value():\n    return new()\n")
    (root / "b.py").write_text("def old():\n    return 1\n\ndef new():\n    return 2\n")
    reloader.on_reload_file(str(root / "a.py"))
    reloader.on_reload_file(str(root / "b.py"))

    qtbot.waitUntil(lambda: len(emitted) == 2, timeout=2000)
    assert emitted == [f"{name}.b", f"{name}.a"]
    assert mod_a.value() == 2


def test_order_by_imports(make_reloader, make_package):
    """Test chains keep dependencies first, unrelated files keep natural order and cycles do not hang."""
    name, root = make_package(
        {
            "a.py": "from . import b\n",
            "b.py": "",
            "c.py": "",
            "d.py": "",
            "x.py": "from .y import f\n",
            "y.py": "from .x import g\n",
        }
    )
    (root / "b.py").write_text(f"import {name}.c\n")
    reloader = make_reloader([name])
    paths = [str(root / f"{stem}.py") for stem in ("y", "x", "d", "c", "b", "a")]

    ordered = [Path(path).name for path in reloader._order_by_imports(paths)]
    assert ordered == ["c.py", "b.py", "a.py", "d.py", "x.py", "y.py"]
    assert reloader._order_by_imports([]) == []
    assert len(reloader._order_by_imports([*paths, "/not/watched.py"])) == len(paths) + 1


def test_stylesheet_signal_once_per_batch(qtbot, make_reloader, make_package):
    name, root = make_package({"one.qss": "", "two.qss": ""})
    messages = []
    reloader = make_reloader([name], messages)
    emitted = []
    reloader.evt_stylesheet.connect(lambda: emitted.append(True))

    reloader.on_reload_file(str(root / "one.qss"))
    reloader.on_reload_file(str(root / "two.qss"))
    qtbot.waitUntil(lambda: bool(emitted), timeout=2000)
    qtbot.wait(50)
    assert emitted == [True]
    assert any("'one.qss', 'two.qss' changed" in msg for msg in messages)


def test_reload_result_summary():
    from qtreload.reloader import ReloadResult

    assert ReloadResult("m", "m.py").summary() == "no changes"
    result = ReloadResult("m", "m.py", changed=True, updated=("a", "b", "c"), added=("x",))
    assert result.ok
    assert result.summary() == "updated a, b, c; added x"
    assert result.summary(max_names=2) == "updated a, b (+1 more); added x"
    failed = ReloadResult("m", "m.py", error=ValueError("boom"))
    assert not failed.ok
    assert failed.summary() == "ValueError: boom"


def test_reload_result_signals(qtbot, make_reloader, make_package):
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    reloader = make_reloader([name])
    failed = []
    reloader.evt_reload_failed.connect(failed.append)
    path = str(root / "a.py")

    reloaded, pyfiles = [], []
    reloader.evt_reloaded.connect(reloaded.append)
    reloader.evt_pyfile.connect(pyfiles.append)

    (root / "a.py").write_text("def value():\n    return 2\n\ndef extra():\n    return 3\n")
    result = reloader.reload_path(path)
    assert reloaded == [result]
    assert pyfiles == [f"{name}.a"]
    assert result.module == f"{name}.a"
    assert result.path == path
    assert result.ok
    assert result.changed
    assert result.updated == ("value",)
    assert result.added == ("extra",)
    assert result.traceback == ""
    assert failed == []

    (root / "a.py").write_text("def value(:\n")
    with qtbot.waitSignal(reloader.evt_reload_failed) as blocker, qtbot.assertNotEmitted(reloader.evt_reloaded):
        result = reloader.reload_path(path)
    assert blocker.args == [result]
    assert not result.ok
    assert isinstance(result.error, SyntaxError)
    assert "SyntaxError" in result.traceback
    assert not result.changed


def test_reload_path_without_result(make_reloader, make_package):
    name, root = make_package({"a.py": "", "style.qss": ""})
    reloader = make_reloader([name])
    assert reloader.reload_path(str(root / "a.py")) is None, "Module was never imported"
    assert reloader.reload_path(str(root / "style.qss")) is None


def test_messages_have_levels(qtbot, make_reloader, make_package, monkeypatch):
    import logging

    from qtreload import reloader as reloader_module

    monkeypatch.setattr(reloader_module, "MAX_MESSAGES", 20)  # small cap, emitting 1000+ messages aborts Python 3.10 + PySide6 at exit
    name, root = make_package({"a.py": "def value():\n    return 1\n"})
    importlib.import_module(f"{name}.a")
    reloader = make_reloader([name, "not_a_module_qtreload"])
    assert any("Could not find path" in msg and level == logging.WARNING for msg, level in reloader.messages)
    assert any("Watching for" in msg and level == logging.INFO for msg, level in reloader.messages)

    (root / "a.py").write_text("def value(:\n")
    with qtbot.waitSignal(reloader.evt_message) as blocker:
        reloader.reload_path(str(root / "a.py"))
    assert "SyntaxError" in blocker.args[0]
    assert blocker.args[1] == logging.ERROR
    assert reloader.messages[-1] == tuple(blocker.args)

    for i in range(reloader_module.MAX_MESSAGES + 5):
        reloader.log_message(f"message {i}")
    assert len(reloader.messages) == reloader_module.MAX_MESSAGES
    assert reloader.messages[-1][0].endswith(f"message {reloader_module.MAX_MESSAGES + 4}")
