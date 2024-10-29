from pathlib import Path

import pytest
from qtreload.utilities import get_import_path, path_to_module, IS_WIN, get_module_paths

if IS_WIN:
    to_test = [
        ("C:\\Users\\user\\Documents\\test\\functions.py", Path("C:\\Users\\user\\Documents\\test"), "test.functions"),
        (
            "C:\\Users\\user\\Documents\\src\\test\\functions.py",
            Path("C:\\Users\\user\\Documents\\src\\test"),
            "test.functions",
        ),
        (
            "C:\\Users\\user\\Documents\\site-packages\\test\\functions.py",
            Path("C:\\Users\\user\\Documents\\site-packages\\test"),
            "test.functions",
        ),
    ]
else:
    to_test = [
        ("/home/user/Documents/test/functions.py", Path("/home/user/Documents/test"), "test.functions"),
        ("/home/user/Documents/src/test/functions.py", Path("/home/user/Documents/src/test"), "test.functions"),
        (
            "/home/user/Documents/site-packages/test/functions.py",
            Path("/home/user/Documents/site-packages/test"),
            "test.functions",
        ),
    ]


@pytest.mark.parametrize("path, module, expected", to_test)
def test_path_to_module(path, module, expected):
    """Test conversion of 'path' to 'module'."""
    assert path_to_module(path, module) == expected


@pytest.mark.parametrize("module", ["qtreload"])
def test_get_import_path(module):
    """Test getting a module path."""
    path = get_import_path(module)
    assert path is not None
    assert path.exists()


@pytest.mark.parametrize(
    "module, py_pattern, ignore_py_pattern, stylesheet_pattern",
    [
        ("qtreload", ("**/*.py",), ("**/__init__.py", "**/test_*.py"), ("**/*.qss",)),
    ],
)
def test_get_module_paths(module, py_pattern, ignore_py_pattern, stylesheet_pattern):
    """Test getting module paths."""
    module_paths, stylesheet_paths = get_module_paths(
        module, py_pattern=py_pattern, ignore_py_pattern=ignore_py_pattern, stylesheet_pattern=stylesheet_pattern
    )
    assert len(module_paths) > 0
    assert len(stylesheet_paths) == 0
    for module_path in module_paths:
        assert module_path.exists()
    for stylesheet_path in stylesheet_paths:
        assert stylesheet_path.exists()


def test_get_module_paths_with_init():
    """Test getting module paths."""
    module_paths, stylesheet_paths = get_module_paths("qtreload", ignore_py_pattern=())
    assert len(module_paths) > 0
    assert len(stylesheet_paths) == 0
    for module_path in module_paths:
        assert module_path.exists()
    assert any(path.name == "__init__.py" for path in module_paths), "Expected __init__.py in module paths."


def test_get_module_paths_error():
    """Test getting module paths."""
    with pytest.raises(ValueError):
        get_module_paths("not_a_module")
