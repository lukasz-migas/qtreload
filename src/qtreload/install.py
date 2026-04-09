"""Install hot-reload module."""

from __future__ import annotations

import os

from qtpy.QtWidgets import QWidget

from qtreload.qt_reload import QtReloadWidget

# store reference to QtReloadWidget to prevent garbage collection
_reload_ref = None


def _parse_modules(raw_modules: str) -> list[str]:
    """Parse and deduplicate the configured module list while preserving order."""
    modules: list[str] = []
    seen: set[str] = set()
    for module in raw_modules.split(","):
        stripped_module = module.strip()
        if not stripped_module or stripped_module in seen:
            continue
        seen.add(stripped_module)
        modules.append(stripped_module)
    return modules


def install_hot_reload(parent: QWidget | None = None) -> QtReloadWidget | None:
    """Install or update the singleton hot-reload widget for development use."""
    global _reload_ref

    run_reload = os.environ.get("QTRELOAD_HOT_RELOAD", "0") == "1"
    if not run_reload:
        _reload_ref = None
        return None

    modules = _parse_modules(os.environ.get("QTRELOAD_HOT_RELOAD_MODULES", ""))
    if _reload_ref is None:
        _reload_ref = QtReloadWidget(modules, parent=parent)
    else:
        _reload_ref.replace_modules(modules)
    return _reload_ref
