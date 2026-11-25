"""Install hot-reload module."""

from __future__ import annotations

import os

from qtpy.QtWidgets import QWidget

from qtreload.config import load_config
from qtreload.qt_reload import QtReloadWidget

# store reference to QtReloadWidget to prevent garbage collection
_reload_ref = None


def install_hot_reload(parent: QWidget | None = None, settings_key: str | None = None) -> QtReloadWidget | None:
    """Install or update the singleton hot-reload widget for development use.

    Nothing is done unless the environment variable `QTRELOAD_HOT_RELOAD` is "1". The modules and patterns come from
    `qtreload.config.load_config` ([tool.qtreload] in pyproject.toml and environment variables such as
    `QTRELOAD_HOT_RELOAD_MODULES`). Calling it again applies the current configuration to the existing widget.

    Parameters
    ----------
    parent : QWidget, optional
        Parent of the widget when it is created.
    settings_key : str, optional
        Remember edits made in the widget under this key (see `HotReloader`). Only used when the widget is created.
    """
    global _reload_ref

    run_reload = os.environ.get("QTRELOAD_HOT_RELOAD", "0") == "1"
    if not run_reload:
        _reload_ref = None
        return None

    config = load_config()
    if _reload_ref is None:
        _reload_ref = QtReloadWidget(
            config.modules,
            parent=parent,
            settings_key=settings_key,
            editor=config.editor,
            **config.reloader_kwargs(),
        )
    else:
        _reload_ref.reloader.py_pattern = config.py_pattern
        _reload_ref.reloader.ignore_py_pattern = config.ignore_py_pattern
        _reload_ref.reloader.stylesheet_pattern = config.stylesheet_pattern
        _reload_ref.replace_modules(config.modules)
    return _reload_ref
