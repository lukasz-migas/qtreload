import importlib

import pytest

from qtreload.pydevd_reload import Reload, xreload


def test_xreload_updates_function_in_place(make_package):
    name, root = make_package({"mod.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.mod")
    func = mod.value
    (root / "mod.py").write_text("def value():\n    return 2\n")

    assert xreload(mod) is True
    assert func() == 2


def test_xreload_raises_on_syntax_error(make_package):
    name, root = make_package({"mod.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.mod")
    (root / "mod.py").write_text("def value(:\n")

    with pytest.raises(SyntaxError):
        xreload(mod)
    assert mod.value() == 1


def test_reload_collects_warnings(make_package):
    name, root = make_package({"mod.py": "def value():\n    return 1\n"})
    mod = importlib.import_module(f"{name}.mod")
    (root / "mod.py").write_text("value = 2\n")

    reloader = Reload(mod)
    reloader.apply()
    assert reloader.error is None
    assert any("value" in warning for warning in reloader.warnings)


def test_reload_with_relative_imports(make_package):
    """Test relative imports work in reloaded modules and package __init__ files."""
    name, root = make_package({"b.py": "def old():\n    return 1\n", "a.py": "from .b import old\n"})
    (root / "__init__.py").write_text("from .b import old\n")
    importlib.invalidate_caches()
    package = importlib.import_module(name)
    mod_a = importlib.import_module(f"{name}.a")

    for mod in (mod_a, package):
        reloader = Reload(mod)
        reloader.apply()
        assert reloader.error is None, reloader.error


def test_reload_tracks_added_and_updated_names(make_package):
    old_source = (
        "def f():\n    return 1\n\n"
        "class C:\n    def m(self):\n        return 1\n\n    def same(self):\n        return 0\n"
    )
    new_source = (
        "def f():\n    return 2\n\ndef g():\n    return 3\n\n"
        "class C:\n    def m(self):\n        return 2\n\n    def same(self):\n        return 0\n\n"
        "    def n(self):\n        return 4\n"
    )
    name, root = make_package({"mod.py": old_source})
    mod = importlib.import_module(f"{name}.mod")
    (root / "mod.py").write_text(new_source)

    reloader = Reload(mod)
    reloader.apply()
    assert reloader.error is None
    assert sorted(reloader.updated) == ["C.m", "f"]
    assert sorted(reloader.added) == ["C.n", "g"]


def test_code_objects_equal_ignores_line_numbers():
    import warnings

    from qtreload.pydevd_reload import code_objects_equal

    code = compile("def f(self):\n    return 0\n", "x", "exec").co_consts[0]
    moved = compile("\n\ndef f(self):\n    return 0\n", "x", "exec").co_consts[0]
    changed = compile("def f(self):\n    return 1\n", "x", "exec").co_consts[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert code_objects_equal(code, moved)
        assert not code_objects_equal(code, changed)
