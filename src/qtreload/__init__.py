"""Qt utilities to enable hot-reloading of python/Qt code."""
from importlib.metadata import PackageNotFoundError, version
from qtreload.qt_reload import QtReloadWidget
from qtreload.install import install_hot_reload

try:
    __version__ = version("qtreload")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Lukasz G. Migas"
__email__ = "lukas.migas@yahoo.com"
__all__ = ["QtReloadWidget", "install_hot_reload"]