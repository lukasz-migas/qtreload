from pathlib import Path

import pytest
from qtreload.qt_reload import QtReloadWidget, get_import_path, path_to_module


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


def test_widget(qtbot):
    """Test widget."""
    widget = QtReloadWidget(["qtreload"])
    qtbot.addWidget(widget)
    assert widget is not None
    assert len(widget.path_to_index_map) > 0, "Expected more than 1 path"

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map.keys():
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"
