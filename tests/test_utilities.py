from pathlib import Path

import pytest
from qtreload.utilities import get_import_path, path_to_module


@pytest.mark.parametrize(
    "path, module, expected",
    [
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
    ],
)
def test_path_to_module(path, module, expected):
    """Test conversion of 'path' to 'module'."""
    assert path_to_module(path, module) == expected


@pytest.mark.parametrize("module", ["qtreload", "superqt"])
def test_get_import_path(module):
    """Test getting a module path."""
    path = get_import_path(module)
    assert path is not None
    assert path.exists()
