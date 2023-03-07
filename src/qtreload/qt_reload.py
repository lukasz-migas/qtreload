"""Hot-reload widget."""
import importlib
import pkgutil
import os
import typing as ty
from pathlib import Path
from logging import getLogger

from qtpy.QtCore import QFileSystemWatcher, Signal
from qtpy.QtWidgets import QHBoxLayout, QLabel, QWidget
from superqt.utils import qthrottled

from qtreload.pydevd_reload import xreload


logger = getLogger(__name__)

# store reference to QtReloadWidget to prevent garbage collection
_reload_ref = None


def install_hot_reload(parent):
    """Install hot-reload module - recommended for developers only."""
    global _reload_ref

    run_reload = os.environ.get('QTRELOAD_HOT_RELOAD', '0') == '1'
    if run_reload and _reload_ref is None:
        modules = os.environ.get("QTRELOAD_HOT_RELOAD_MODULES", "")
        # split modules separated by comma
        modules = modules.split(",") if modules else []
        # remove empty strings
        modules = [module.strip() for module in modules]
        # initialize widget
        _reload_ref = QtReloadWidget(list(set(modules)), parent=parent)
    return _reload_ref


def get_import_path(module: str) -> ty.Optional[Path]:
    """Get module path."""
    module = pkgutil.get_loader(module)
    if module is None:
        return None
    path = Path(module.get_filename())
    return path.parent


def path_to_module(path: str) -> str:
    """Turn path into module name."""
    module = path.split("src\\")[1]
    return module.replace("\\", ".").replace(".py", "")


def get_parent_module(module: str):
    """Get parent module."""
    return ".".join(module.split(".")[:-1])


class QtReloadWidget(QWidget):
    """Reload Widget"""

    evt_theme = Signal()

    def __init__(
        self, modules: ty.Iterable[str], parent=None, auto_connect: bool = True
    ):
        super().__init__(parent=parent)
        self._watcher = QFileSystemWatcher()

        self._info = QLabel()
        layout = QHBoxLayout()
        layout.addWidget(self._info, stretch=True)
        self.setLayout(layout)

        self._paths = [get_import_path(module) for module in modules]
        logger.debug(f"Watching {self._paths} for changes")
        if self._paths and auto_connect:
            self.setup_paths()

    def setup_paths(self):
        """Setup paths.""" ""
        self._add_filenames()
        self._watcher.fileChanged.connect(self.on_reload_file)
        # self._add_directories()
        # self._watcher.directoryChanged.connect(self.on_reload_directory)

    def _add_filenames(self):
        """Set paths."""
        paths = []
        for _path in self._paths:
            if _path:
                paths += self._get_file_paths(_path)
        self._set_paths(paths)

    @staticmethod
    def _get_file_paths(path: Path):
        paths = []
        py = 0
        for new_path in path.glob("**/*.py"):
            if new_path.name == "__init__.py":
                continue
            paths.append(str(new_path))
            py += 1
        # get list of qss files
        qss = 0
        for new_path in path.glob("**/*.qss"):
            paths.append(str(new_path))
            qss += 1
        paths = list(set(paths))
        logger.debug(
            f"Found {py} python files and {qss} qss files '{path.name}'"
        )
        return paths

    def _add_directories(self):
        """Set paths."""
        paths = []
        for _path in self._paths:
            paths += self._get_directories(_path)
        self._set_paths(paths)

    @staticmethod
    def _get_directories(path: Path):
        paths = []
        dirs = 0
        for new_path in path.glob("**/*.py"):
            if new_path.name == "__init__.py":
                continue
            paths.append(str(new_path.parent))
            dirs += 1
        paths = list(set(paths))
        logger.debug(f"Found {len(paths)} directories for '{path.name}'")
        return paths

    def _set_paths(self, paths: ty.List[str]):
        logger.debug(f"Added {len(paths)} paths to watcher")
        if paths:
            self._watcher.addPaths(paths)
            self._info.setText(f"Added {len(paths)} paths to watcher")

    @qthrottled(timeout=500, leading=False)
    def on_reload_file(self, path: str):
        """Reload all modules."""
        self._reload_file(path)

    def _reload_file(self, path: str):
        if path.endswith(".py"):
            self._reload(path)
        elif path.endswith(".qss"):
            self.evt_theme.emit()
            logger.debug(f"Stylesheet '{path}' changed...")

    def _reload(self, path: str):
        module = path_to_module(path)
        logger.debug(f"'{path}' changed...")
        try:
            res = xreload(importlib.import_module(module))
            self._info.setText(f"'{module}' (changed={res})")
            logger.debug(f"Module '{module}' (changed={res})")
        except Exception as e:
            logger.debug(f"Failed to reload '{path}' {module}' Error={e}...")

    def on_reload_directory(self, path: str):
        """Reload all modules in directory."""
        paths = self._get_file_paths(Path(path))
        logger.debug(f"'{path}' changed, reloading '{len(paths)} modules'...")
        for path in paths:
            self._reload_file(path)
