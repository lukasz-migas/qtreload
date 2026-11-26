"""Qt utilities to enable hot-reloading of python/Qt code."""

from importlib.metadata import PackageNotFoundError, version

from qtreload.config import ReloadConfig, load_config
from qtreload.inspector import WidgetInspector, describe_widget, open_in_editor
from qtreload.install import install_hot_reload
from qtreload.launch import install_dev_tools
from qtreload.live import LiveWidget, replace_widget
from qtreload.qt_reload import QtDevPopup, QtReloadWidget
from qtreload.reloader import HotReloader, ReloadResult
from qtreload.utilities import render_stylesheet

try:
    __version__ = version("qtreload")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Lukasz G. Migas"
__email__ = "lukas.migas@yahoo.com"
__all__ = [
    "HotReloader",
    "LiveWidget",
    "QtDevPopup",
    "QtReloadWidget",
    "ReloadConfig",
    "ReloadResult",
    "WidgetInspector",
    "describe_widget",
    "install_dev_tools",
    "install_hot_reload",
    "load_config",
    "open_in_editor",
    "render_stylesheet",
    "replace_widget",
]
