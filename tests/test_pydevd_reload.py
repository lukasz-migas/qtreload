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


def _load(make_package, source):
    name, root = make_package({"mod.py": source})
    return importlib.import_module(f"{name}.mod"), root / "mod.py"


def _reload(mod, path, source):
    path.write_text(source)
    reloader = Reload(mod)
    reloader.apply()
    assert reloader.error is None, reloader.error
    return reloader


def test_methods_updated_in_place(make_package):
    source = """
class C:
    def method(self):
        return 1

    @classmethod
    def cm(cls):
        return 1

    @staticmethod
    def sm():
        return 1
"""
    mod, path = _load(make_package, source)
    instance = mod.C()
    bound = instance.method
    _reload(mod, path, source.replace("return 1", "return 2"))
    assert bound() == 2
    assert instance.method() == 2
    assert mod.C.cm() == 2
    assert mod.C.sm() == 2


def test_constants_kept_and_new_names_added(make_package):
    mod, path = _load(make_package, "CONSTANT = 1\n")
    reloader = _reload(mod, path, "CONSTANT = 2\nNEW = 3\n")
    assert mod.CONSTANT == 1
    assert mod.NEW == 3
    assert reloader.added == ["NEW"]


def test_property_updated(make_package):
    source = """
class C:
    def __init__(self):
        self._value = 1

    @property
    def value(self):
        return self._value
"""
    mod, path = _load(make_package, source)
    instance = mod.C()
    new_source = (
        source.replace("return self._value", "return self._value * 10")
        + """
    @value.setter
    def value(self, value):
        self._value = value
"""
    )
    reloader = _reload(mod, path, new_source)
    assert instance.value == 10
    instance.value = 2
    assert instance.value == 20
    assert "C.value" in reloader.updated
    assert reloader.warnings == []


def test_wraps_decorated_function_updated(make_package):
    source = """
import functools

def decorator(func):
    @functools.wraps(func)
    def wrapper(*args):
        return func(*args)
    return wrapper

@decorator
def value():
    return 1
"""
    mod, path = _load(make_package, source)
    value = mod.value
    reloader = _reload(mod, path, source.replace("return 1", "return 2"))
    assert value() == 2
    assert "value" in reloader.updated


def test_decorator_without_wraps_updated_through_closure(make_package):
    source = """
def decorator(func):
    def wrapper(*args):
        return func(*args)
    return wrapper

@decorator
def value():
    return 1
"""
    mod, path = _load(make_package, source)
    value = mod.value
    _reload(mod, path, source.replace("return 1", "return 2"))
    assert value() == 2


def test_lru_cache_updated_and_cleared(make_package):
    source = """
import functools

@functools.lru_cache
def value():
    return 1
"""
    mod, path = _load(make_package, source)
    value = mod.value
    assert value() == 1
    _reload(mod, path, source.replace("return 1", "return 2"))
    assert value() == 2


def test_recursive_closure_does_not_loop(make_package):
    source = """
def outer():
    def countdown(n):
        return 1 if n == 0 else countdown(n - 1)
    return countdown

countdown = outer()
"""
    mod, path = _load(make_package, source)
    countdown = mod.countdown
    _reload(mod, path, source.replace("return 1 if", "return 2 if"))
    assert countdown(3) == 2


def test_changed_closure_variables_warn(make_package):
    source = """
def decorator(func):
    def wrapper():
        return func()
    return wrapper

@decorator
def value():
    return 1
"""
    mod, path = _load(make_package, source)
    new_source = source.replace(
        "    def wrapper():\n        return func()",
        "    extra = 1\n\n    def wrapper():\n        return func() + extra",
    )
    reloader = _reload(mod, path, new_source)
    assert any("value" in warning and "restart" in warning for warning in reloader.warnings), reloader.warnings


def test_method_with_new_closure_is_replaced(make_package):
    source = """
class Base:
    def value(self):
        return 1

class Child(Base):
    def value(self):
        return 10
"""
    mod, path = _load(make_package, source)
    instance = mod.Child()
    reloader = _reload(mod, path, source.replace("return 10", "return super().value() + 10"))
    assert instance.value() == 11
    assert "Child.value" in reloader.updated
    assert reloader.warnings == []


def test_dataclass_new_field(make_package):
    source = """
from dataclasses import dataclass

@dataclass
class Point:
    x: int = 0

    def total(self):
        return self.x
"""
    mod, path = _load(make_package, source)
    point_class = mod.Point
    new_source = source.replace("    x: int = 0\n", "    x: int = 0\n    y: int = 5\n").replace(
        "return self.x", "return self.x + self.y"
    )
    reloader = _reload(mod, path, new_source)
    point = point_class(1)
    assert point.y == 5
    assert point.total() == 6
    assert repr(point) == "Point(x=1, y=5)"
    import dataclasses

    assert [field.name for field in dataclasses.fields(point_class)] == ["x", "y"]
    assert reloader.warnings == []


def test_enum_methods_updated_without_warnings(make_package):
    source = """
import enum

class Color(enum.Enum):
    RED = 1
    GREEN = 2

    def label(self):
        return self.name.lower()
"""
    mod, path = _load(make_package, source)
    red = mod.Color.RED
    reloader = _reload(mod, path, source.replace("self.name.lower()", "self.name.title()"))
    assert red.label() == "Red"
    assert reloader.warnings == []
    assert mod.Color(1) is red


def test_enum_member_changes_warn(make_package):
    source = """
import enum

class Color(enum.Enum):
    RED = 1
    GREEN = 2
"""
    mod, path = _load(make_package, source)
    reloader = _reload(mod, path, source.replace("GREEN = 2", "GREEN = 2\n    BLUE = 3"))
    assert len(reloader.warnings) == 1
    assert "Color" in reloader.warnings[0]
    assert "BLUE" in reloader.warnings[0]
    assert "restart" in reloader.warnings[0]


def test_reload_hooks(make_package):
    source = """
CONSTANT = 1
calls = []

def __xreload_old_new__(namespace, name, old, new):
    if name == "CONSTANT":
        namespace[name] = new

def __xreload_after_reload_update__(namespace):
    namespace["calls"].append("module")

class C:
    LIMIT = 1

    @classmethod
    def __xreload_old_new__(cls, name, old, new):
        if name == "LIMIT":
            setattr(cls, name, new)

    @classmethod
    def __xreload_after_reload_update__(cls):
        calls.append("class")
"""
    mod, path = _load(make_package, source)
    _reload(mod, path, source.replace("CONSTANT = 1", "CONSTANT = 2").replace("LIMIT = 1", "LIMIT = 2"))
    assert mod.CONSTANT == 2
    assert mod.C.LIMIT == 2
    assert sorted(mod.calls) == ["class", "module"]


def test_class_hierarchy_change_warns(make_package):
    source = "class A:\n    pass\n\nclass B:\n    pass\n\nclass C(A):\n    pass\n"
    mod, path = _load(make_package, source)
    reloader = _reload(mod, path, source.replace("class C(A)", "class C(B)"))
    assert any("hierarchy" in warning for warning in reloader.warnings)


def test_package_init_reload(make_package):
    name, root = make_package({"core.py": "def run():\n    return 1\n"})
    (root / "__init__.py").write_text("from .core import run\n\ndef version():\n    return 1\n")
    importlib.invalidate_caches()
    package = importlib.import_module(name)
    version = package.version
    (root / "__init__.py").write_text(
        "from .core import run\n\ndef version():\n    return 2\n\ndef extra():\n    return 3\n"
    )

    reloader = Reload(package)
    reloader.apply()
    assert reloader.error is None
    assert version() == 2
    assert package.extra() == 3
