import os

try:
    import qtpy

except Exception:
    qtpy = None

import pytest

from qtreload.utilities import path_to_module


@pytest.mark.skipif(qtpy is None, reason="Qt is required for this test")
def test_widget(qtbot):
    """Test widget."""
    from qtreload.qt_reload import QtReloadWidget

    widget = QtReloadWidget(["qtreload"])
    qtbot.addWidget(widget)
    assert widget is not None
    assert len(widget.path_to_index_map) > 0, "Expected more than 1 path"

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map.keys():
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"


@pytest.mark.skipif(qtpy is None, reason="Qt is required for this test")
def test_install_hot_reload(qtbot):
    """Test installing hot reload."""
    from qtreload.install import install_hot_reload

    os.environ["QTRELOAD_HOT_RELOAD"] = "0"
    widget = install_hot_reload(None)
    assert widget is None

    os.environ["QTRELOAD_HOT_RELOAD"] = "1"
    os.environ["QTRELOAD_HOT_RELOAD_MODULES"] = "qtreload"
    widget = install_hot_reload(None)
    qtbot.addWidget(widget)
    assert widget is not None
    assert len(widget.path_to_index_map) > 0, "Expected more than 1 path"
    assert len(widget._module_paths) == 1, "Expected 2 modules"

    # make sure we can retrieve each module properly
    for path in widget.path_to_index_map.keys():
        module = path_to_module(path, widget.get_module_path_for_path(path))
        assert module, "Module should not be empty"
        paths = widget._get_file_paths(module)
        assert len(paths) > 0, "Expected more than 1 path"
