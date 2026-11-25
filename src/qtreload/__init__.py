"""Qt utilities to enable hot-reloading of python/Qt code."""

from importlib.metadata import PackageNotFoundError, version

from qtreload.install import install_hot_reload
from qtreload.qt_reload import QtDevPopup, QtReloadWidget
from qtreload.reloader import HotReloader, ReloadResult
from qtreload.utilities import render_stylesheet

try:
    __version__ = version("qtreload")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Lukasz G. Migas"
__email__ = "lukas.migas@yahoo.com"
__all__ = ["HotReloader", "QtDevPopup", "QtReloadWidget", "ReloadResult", "install_hot_reload", "render_stylesheet"]
