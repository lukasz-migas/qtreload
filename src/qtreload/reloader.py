"""Headless hot-reload core."""

from __future__ import annotations

import sys
import typing as ty
from datetime import datetime
from logging import getLogger
from pathlib import Path

from natsort import natsorted
from qtpy.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from qtreload.pydevd_reload import Reload
from qtreload.utilities import get_import_path, get_module_paths, path_to_module

logger = getLogger(__name__)

TIME_FMT = "%Y-%m-%d %H:%M:%S"
# delay before processing file changes, so that bursts of saves are handled together
RELOAD_DELAY_MS = 500

PY_PATTERN = ("**/*.py",)
PY_IGNORE_PATTERN = (
    "**/__init__.py",
    "**/_version.py",
    "**/test_*.py",
)
STYLESHEET_PATTERN = ("**/*.qss",)
# directories that are never watched for new files
IGNORE_DIRECTORIES = ("__pycache__",)


class HotReloader(QObject):
    """Watch python modules and stylesheets and hot-reload them when they change.

    The directories of watched packages are watched too, so files that are added or deleted later are picked up
    automatically. This object has no user interface. `QtReloadWidget` provides one on top of it.

    Parameters
    ----------
    modules : Iterable[str]
        Names of the modules (packages, subpackages or single-file modules) to watch.
    parent : QObject, optional
        Qt parent.
    auto_connect : bool
        If True, files are discovered and watched immediately. Otherwise call `setup_paths` to start.
    py_pattern : tuple[str, ...]
        Glob patterns of python files to watch.
    ignore_py_pattern : tuple[str, ...]
        Glob patterns of python files to skip.
    stylesheet_pattern : tuple[str, ...]
        Glob patterns of stylesheet files to watch.
    log_func : Callable[[str], None], optional
        Called with every (timestamped) log message.
    delay_ms : int
        Changes are reloaded once no new change was seen for this many milliseconds.
    """

    # emitted with the module name after it was reloaded successfully
    evt_pyfile = Signal(str)
    # emitted when a stylesheet changed or a stylesheet reload was requested
    evt_stylesheet = Signal()
    # emitted after the watched modules, patterns or files were updated
    evt_watchlist_changed = Signal()

    def __init__(
        self,
        modules: ty.Iterable[str] = (),
        parent: QObject | None = None,
        auto_connect: bool = True,
        py_pattern: tuple[str, ...] = PY_PATTERN,
        ignore_py_pattern: tuple[str, ...] = PY_IGNORE_PATTERN,
        stylesheet_pattern: tuple[str, ...] = STYLESHEET_PATTERN,
        log_func: ty.Callable[[str], None] | None = None,
        delay_ms: int = RELOAD_DELAY_MS,
    ) -> None:
        super().__init__(parent)
        self.log_func = log_func
        self.py_pattern = py_pattern
        self.ignore_py_pattern = ignore_py_pattern
        self.stylesheet_pattern = stylesheet_pattern

        self._watcher = QFileSystemWatcher(self)
        self._watcher_connected = False

        self._pending_paths: set[str] = set()
        self._pending_directories: set[str] = set()
        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(delay_ms)
        self._reload_timer.timeout.connect(self._process_pending_paths)

        self._modules: list[str] = []
        self._module_paths: list[Path] = []
        self.path_to_index_map: dict[str, int] = {}
        self._directory_to_index_map: dict[str, int] = {}
        for module in modules:
            if module in self._modules:
                continue
            path = self._resolve_module(module)
            if path:
                self._modules.append(module)
                self._module_paths.append(path)
        if auto_connect:
            self.setup_paths()

    @property
    def modules(self) -> tuple[str, ...]:
        """Names of the watched modules."""
        return tuple(self._modules)

    @property
    def files(self) -> list[str]:
        """Discovered python and stylesheet files, sorted."""
        return natsorted(self.path_to_index_map)

    # Watch list management

    def add_module(self, module: str) -> bool:
        """Start watching `module`. Returns True if it was added."""
        if module in self._modules:
            self.log_message(f"The module '{module}' is already in the list.")
            return False
        path = self._resolve_module(module)
        if not path:
            return False
        self._modules.append(module)
        self._module_paths.append(path)
        self.refresh()
        return True

    def remove_modules(self, modules: ty.Iterable[str]) -> None:
        """Stop watching `modules`. Unknown names are ignored."""
        to_remove = set(modules)
        kept = [(m, p) for m, p in zip(self._modules, self._module_paths, strict=True) if m not in to_remove]
        self._modules = [m for m, _ in kept]
        self._module_paths = [p for _, p in kept]
        self.refresh()

    def replace_modules(self, modules: ty.Iterable[str]) -> None:
        """Replace the watched module list and refresh watched paths."""
        self._modules = []
        self._module_paths = []
        for module in modules:
            if module in self._modules:
                continue
            path = self._resolve_module(module)
            if path is None:
                continue
            self._modules.append(module)
            self._module_paths.append(path)
        self.refresh()

    def set_patterns(
        self,
        py_pattern: tuple[str, ...] | None = None,
        ignore_py_pattern: tuple[str, ...] | None = None,
        stylesheet_pattern: tuple[str, ...] | None = None,
    ) -> None:
        """Update the file patterns (None keeps the current value) and refresh watched paths."""
        if py_pattern is not None:
            self.py_pattern = py_pattern
        if ignore_py_pattern is not None:
            self.ignore_py_pattern = ignore_py_pattern
        if stylesheet_pattern is not None:
            self.stylesheet_pattern = stylesheet_pattern
        self.refresh()

    def refresh(self) -> None:
        """Rediscover files of all watched modules."""
        self.setup_paths(clear=True, connect=False)

    def setup_paths(self, clear: bool = False, connect: bool = True) -> None:
        """Discover and watch files, optionally clearing the previous ones and connecting the watcher."""
        if clear:
            self._remove_filenames()
        self._add_filenames()
        if connect and not self._watcher_connected:
            self._watcher.fileChanged.connect(self.on_reload_file)
            self._watcher.directoryChanged.connect(self.on_directory_changed)
            self._watcher_connected = True
        self.evt_watchlist_changed.emit()

    def _resolve_module(self, module: str) -> Path | None:
        """Return the import path of `module`, logging the outcome."""
        try:
            path = get_import_path(module)
        except ValueError:
            path = None
        if path is None:
            self.log_message(f"Could not find path for the module '{module}'")
        else:
            self.log_message(f"Watching for '{module}' changes in '{path}'")
        return path

    def _remove_filenames(self) -> None:
        """Stop watching all files and directories."""
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)
        directories = self._watcher.directories()
        if directories:
            self._watcher.removePaths(directories)
        self.log_message(f"Removed {len(files)} files and {len(directories)} directories from watcher.")

    def _add_filenames(self) -> None:
        """Discover and watch the files and directories of all modules."""
        all_paths: list[str] = []
        all_directories: list[str] = []
        mapping: dict[str, int] = {}
        directory_mapping: dict[str, int] = {}
        for i, module in enumerate(self._modules):
            try:
                paths = self._get_file_paths(module)
            except ValueError as e:
                self.log_message(f"Could not discover files of '{module}': {e}")
                continue
            self.log_message(f"Found {len(paths)} files in '{module}'")
            all_paths += paths
            for path in paths:
                mapping[path] = i
            directories = self._get_directories(i)
            all_directories += directories
            for directory in directories:
                directory_mapping[directory] = i
        self.log_message(f"Added {len(all_paths)} files and {len(set(all_directories))} directories to watcher")
        if all_paths:
            self._watcher.addPaths(all_paths)
        if all_directories:
            self._watcher.addPaths(all_directories)
        self.path_to_index_map = mapping
        self._directory_to_index_map = directory_mapping

    def _get_file_paths(self, module: str) -> list[str]:
        """Get python and stylesheet files of `module`."""
        py_paths, qss_paths = get_module_paths(
            module,
            py_pattern=self.py_pattern,
            ignore_py_pattern=self.ignore_py_pattern,
            stylesheet_pattern=self.stylesheet_pattern,
            log_func=self.log_message,
        )
        return [str(p) for p in py_paths + qss_paths]

    def _get_directories(self, index: int) -> list[str]:
        """Get the directories of a package module, which are watched to discover new or deleted files.

        Single-file modules return nothing, as their parent directory is usually shared with unrelated files.
        """
        root = self._module_paths[index].resolve()
        if not root.is_dir():
            return []
        directories = [root]
        for path in root.rglob("*"):
            parts = path.relative_to(root).parts
            if any(part.startswith(".") or part in IGNORE_DIRECTORIES for part in parts):
                continue
            if path.is_dir():
                directories.append(path)
        return [str(directory) for directory in directories]

    # Path lookup

    def get_module_path_for_path(self, path: str) -> Path:
        """Return the import path of the watched module that `path` belongs to."""
        index = self.path_to_index_map.get(path, None)
        if index is None:
            raise ValueError("Path not found in module paths")
        return self._module_paths[index]

    def get_module_for_path(self, path: str) -> str:
        """Map a watched file path to its fully qualified module name."""
        index = self.path_to_index_map.get(path, None)
        if index is None:
            raise ValueError("Path not found in module paths")
        return path_to_module(path, self._module_paths[index], self._modules[index])

    # Discovery

    def on_directory_changed(self, path: str) -> None:
        """Queue the module owning directory `path` for rediscovery once file changes settle."""
        self._pending_directories.add(path)
        self._reload_timer.start()

    def _discover_pending_directories(self) -> None:
        """Rediscover the files of modules whose directories changed."""
        indices = {
            self._directory_to_index_map[d] for d in self._pending_directories if d in self._directory_to_index_map
        }
        self._pending_directories.clear()
        changed = False
        for index in sorted(indices):
            changed |= self._discover_module(index)
        if changed:
            self.evt_watchlist_changed.emit()

    def _discover_module(self, index: int) -> bool:
        """Watch new files and directories of a module and forget deleted ones. Returns True if files changed."""
        module = self._modules[index]
        try:
            files = set(self._get_file_paths(module))
        except ValueError:
            files = set()
        directories = set(self._get_directories(index))

        old_files = {path for path, i in self.path_to_index_map.items() if i == index}
        old_directories = {path for path, i in self._directory_to_index_map.items() if i == index}
        added_files = files - set(self.path_to_index_map)
        removed_files = old_files - files
        added_directories = directories - set(self._directory_to_index_map)
        removed_directories = old_directories - directories

        for path in removed_files:
            del self.path_to_index_map[path]
        for path in added_files:
            self.path_to_index_map[path] = index
        for path in removed_directories:
            del self._directory_to_index_map[path]
        for path in added_directories:
            self._directory_to_index_map[path] = index

        # stop watching what was deleted and (re-)watch everything else, which also covers paths dropped by the
        # watcher after an editor replaced the file
        watched = set(self._watcher.files()) | set(self._watcher.directories())
        to_remove = (removed_files | removed_directories) & watched
        if to_remove:
            self._watcher.removePaths(natsorted(to_remove))
        to_add = (files | directories) - watched
        if to_add:
            self._watcher.addPaths(natsorted(to_add))

        if added_files or removed_files:
            self.log_message(f"Discovered {len(added_files)} new and {len(removed_files)} deleted files in '{module}'")
            return True
        return False

    # Reloading

    def on_reload_file(self, path: str) -> None:
        """Queue `path` for reloading once file changes settle."""
        self._pending_paths.add(path)
        self._reload_timer.start()

    def _process_pending_paths(self) -> None:
        """Rediscover changed directories, then reload all queued paths."""
        self._discover_pending_directories()
        paths = natsorted(self._pending_paths)
        self._pending_paths.clear()
        watched = set(self._watcher.files())
        for path in paths:
            if path not in self.path_to_index_map:
                # module was removed from the watch list while the change was pending
                continue
            if not Path(path).exists():
                self.log_message(f"'{path}' no longer exists - skipping")
                continue
            # editors that save by replacing the file cause the watcher to drop the path, so add it back
            if path not in watched:
                self._watcher.addPath(path)
            self.reload_path(path)

    def reload_path(self, path: str) -> None:
        """Reload a python or stylesheet file immediately."""
        if path.endswith(".py"):
            self._reload_py(path)
        elif path.endswith(".qss"):
            self._reload_qss(path)

    def reload_all_py(self) -> None:
        """Reload all watched python files."""
        for path in self.files:
            if path.endswith(".py"):
                self._reload_py(path)

    def reload_stylesheets(self) -> None:
        """Ask listeners to re-apply stylesheets."""
        self.log_message("Reloading all stylesheet files...")
        self.evt_stylesheet.emit()

    def _reload_py(self, path: str) -> None:
        try:
            module = self.get_module_for_path(path)
        except ValueError as e:
            self.log_message(f"failed to reload '{path}' Error={e}...")
            return
        mod = sys.modules.get(module)
        if mod is None:
            self.log_message(f"'{module}' has not been imported yet - skipping")
            return
        reloader = Reload(mod)
        reloader.apply()
        for warning in reloader.warnings:
            self.log_message(f"'{module}': {warning}")
        if reloader.error is not None:
            error = reloader.error
            self.log_message(f"failed to reload '{module}' Error={type(error).__name__}: {error}")
            return
        self.log_message(f"'{module}' (changed={reloader.found_change})")
        self.evt_pyfile.emit(module)

    def _reload_qss(self, path: str) -> None:
        self.evt_stylesheet.emit()
        self.log_message(f"'{Path(path).name}' changed")

    def log_message(self, msg: str) -> None:
        """Timestamp `msg` and pass it to the logger and `log_func`."""
        msg = f"{datetime.now().strftime(TIME_FMT)} - {msg}"
        logger.debug(msg)
        if self.log_func is not None:
            self.log_func(msg)
