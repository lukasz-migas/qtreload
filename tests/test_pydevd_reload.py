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
