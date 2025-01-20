"""Install hot-reload module."""

from __future__ import annotations

import os

from qtpy.QtWidgets import QWidget

from qtreload.qt_reload import QtReloadWidget

# store reference to QtReloadWidget to prevent garbage collection
_reload_ref = None


def install_hot_reload(parent: QWidget | None = None) -> QtReloadWidget | None:
    """Install hot-reload module - recommended for developers only."""
    global _reload_ref

    run_reload = os.environ.get("QTRELOAD_HOT_RELOAD", "0") == "1"
    if run_reload and _reload_ref is None:
        modules = os.environ.get("QTRELOAD_HOT_RELOAD_MODULES", "")
        # split modules separated by comma
        modules = modules.split(",") if modules else []
        # remove empty strings
        modules = [module.strip() for module in modules]
        # initialize widget
        _reload_ref = QtReloadWidget(list(set(modules)), parent=parent)
    return _reload_ref
