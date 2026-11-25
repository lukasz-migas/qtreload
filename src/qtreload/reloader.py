"""Headless hot-reload core."""

from __future__ import annotations

import heapq
import logging
import sys
import traceback
import typing as ty
import weakref
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from natsort import natsorted
from qtpy.QtCore import QCoreApplication, QFileSystemWatcher, QObject, QTimer, Signal

from qtreload.pydevd_reload import Reload
from qtreload.utilities import (
    get_import_path,
    get_imported_modules,
    get_module_paths,
    path_to_module,
    render_stylesheet,
)

logger = logging.getLogger(__name__)

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
# number of recent log messages kept in `HotReloader.messages`
MAX_MESSAGES = 1000


# values of stylesheet template variables, or a function returning them (e.g. the colors of the current theme)
StylesheetVariables = ty.Mapping[str, object] | ty.Callable[[], ty.Mapping[str, object]]


class Stylable(ty.Protocol):
    """Anything a stylesheet can be applied to, e.g. QApplication or QWidget."""

    def setStyleSheet(self, stylesheet: str) -> None:
        """Set the stylesheet."""


@dataclass
class _StylesheetRegistration:
    path: str
    target: weakref.ref[Stylable]
    variables: StylesheetVariables | None


@dataclass(frozen=True)
class ReloadResult:
    """Outcome of reloading one python module.

    Attributes
    ----------
    module : str
        Name of the module.
    path : str
        Path of the module file.
    changed : bool
        Whether anything was updated or added.
    added : tuple[str, ...]
        Names added to the module or its classes, e.g. 'new_function' or 'MyClass.new_method'.
    updated : tuple[str, ...]
        Functions and methods whose code changed, e.g. 'function' or 'MyClass.method'.
    warnings : tuple[str, ...]
        Problems that did not stop the reload, e.g. attributes whose type changed and were skipped.
    error : BaseException, optional
        Exception raised while executing the new code. Nothing was updated if set.
    traceback : str
        Formatted traceback of `error`, empty if there is no error.
    """

    module: str
    path: str
    changed: bool = False
    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: BaseException | None = None
    traceback: str = ""

    @property
    def ok(self) -> bool:
        """Whether the module was reloaded without error."""
        return self.error is None

    def summary(self, max_names: int = 5) -> str:
        """Short description of the outcome, listing at most `max_names` names per category."""
        if self.error is not None:
            return f"{type(self.error).__name__}: {self.error}"
        parts = []
        for label, names in (("updated", self.updated), ("added", self.added)):
            if names:
                shown = ", ".join(names[:max_names])
                more = f" (+{len(names) - max_names} more)" if len(names) > max_names else ""
                parts.append(f"{label} {shown}{more}")
        return "; ".join(parts) if parts else "no changes"


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
        Called with every (timestamped) log message. See also `evt_message` and `messages`.
    delay_ms : int
        Changes are reloaded once no new change was seen for this many milliseconds.
    """

    # emitted with the module name after it was reloaded successfully
    evt_pyfile = Signal(str)
    # emitted with the `ReloadResult` after a module was reloaded successfully
    evt_reloaded = Signal(object)
    # emitted with the `ReloadResult` after a module failed to reload
    evt_reload_failed = Signal(object)
    # emitted with every (timestamped) log message and its logging level (e.g. logging.WARNING)
    evt_message = Signal(str, int)
    # emitted when a stylesheet changed or a stylesheet reload was requested
    evt_stylesheet = Signal()
    # emitted with the path of every stylesheet that changed
    evt_stylesheet_changed = Signal(str)
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
        self._messages: deque[tuple[str, int]] = deque(maxlen=MAX_MESSAGES)
        self._stylesheets: list[_StylesheetRegistration] = []
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
    def messages(self) -> list[tuple[str, int]]:
        """Recent log messages as (message, logging level), oldest first."""
        return list(self._messages)

    @property
    def files(self) -> list[str]:
        """Discovered python and stylesheet files and registered stylesheets, sorted."""
        return natsorted(set(self.path_to_index_map) | set(self.stylesheets))

    @property
    def stylesheets(self) -> list[str]:
        """Paths of the stylesheets registered with `register_stylesheet`, in registration order."""
        return list(dict.fromkeys(registration.path for registration in self._stylesheets))

    # Stylesheets

    def register_stylesheet(
        self,
        path: str | Path,
        target: Stylable | None = None,
        variables: StylesheetVariables | None = None,
    ) -> None:
        """Apply the stylesheet at `path` to `target` now and every time the file changes.

        Parameters
        ----------
        path : str | Path
            Stylesheet file. It does not have to belong to a watched module.
        target : QApplication | QWidget, optional
            Object to apply the stylesheet to, the QApplication if not given. It is not kept alive by the reloader.
            When several stylesheets are registered for the same target, they are joined in registration order.
        variables : Mapping[str, object] | Callable[[], Mapping[str, object]], optional
            Values of `{{ name }}` placeholders in the stylesheet, or a function returning them (called each time
            the stylesheet is applied). Placeholders are left unchanged if not given.
        """
        resolved = str(Path(path).resolve())
        if not Path(resolved).is_file():
            raise FileNotFoundError(f"Stylesheet '{path}' does not exist.")
        if target is None:
            target = ty.cast("Stylable | None", QCoreApplication.instance())
            if target is None:
                raise RuntimeError("Create a QApplication before registering a stylesheet without a target.")

        for registration in self._stylesheets:
            if registration.path == resolved and registration.target() is target:
                registration.variables = variables
                break
        else:
            self._stylesheets.append(_StylesheetRegistration(resolved, weakref.ref(target), variables))
        if resolved not in self._watcher.files():
            self._watcher.addPath(resolved)
        self.log_message(f"Registered stylesheet '{Path(resolved).name}'")
        self._apply_stylesheets([resolved])
        self.evt_watchlist_changed.emit()

    def unregister_stylesheet(self, path: str | Path, target: Stylable | None = None) -> None:
        """Stop applying the stylesheet at `path` to `target` (to all targets if not given).

        The stylesheet currently set on the target is not changed.
        """
        resolved = str(Path(path).resolve())
        self._stylesheets = [
            registration
            for registration in self._stylesheets
            if not (registration.path == resolved and (target is None or registration.target() is target))
        ]
        still_needed = resolved in self.path_to_index_map or resolved in self.stylesheets
        if not still_needed and resolved in self._watcher.files():
            self._watcher.removePath(resolved)
        self.evt_watchlist_changed.emit()

    def apply_stylesheets(self) -> None:
        """Re-read and re-apply all registered stylesheets, e.g. after changing their variables."""
        self._apply_stylesheets()

    def _apply_stylesheets(self, paths: ty.Iterable[str] | None = None) -> None:
        """Re-apply the registered stylesheets of targets that use any of `paths` (all targets if None)."""
        self._stylesheets = [registration for registration in self._stylesheets if registration.target() is not None]
        selected = None if paths is None else set(paths)
        targets: list[Stylable] = []
        for registration in self._stylesheets:
            target = registration.target()
            if target is None or (selected is not None and registration.path not in selected):
                continue
            if not any(target is existing for existing in targets):
                targets.append(target)

        for target in targets:
            parts = []
            for registration in self._stylesheets:
                if registration.target() is target:
                    text = self._render_stylesheet(registration)
                    if text is None:
                        break
                    parts.append(text)
            else:
                try:
                    target.setStyleSheet("\n".join(parts))
                except RuntimeError:  # the Qt object was deleted
                    self._stylesheets = [r for r in self._stylesheets if r.target() is not target]

    def _render_stylesheet(self, registration: _StylesheetRegistration) -> str | None:
        """Read a registered stylesheet and fill in its variables. Returns None if the file cannot be read."""
        name = Path(registration.path).name
        try:
            text = Path(registration.path).read_text(encoding="utf-8")
        except OSError as e:
            self.log_message(f"Could not read stylesheet '{name}': {e}", logging.ERROR)
            return None
        if registration.variables is None:
            return text
        variables = registration.variables() if callable(registration.variables) else registration.variables
        text, missing = render_stylesheet(text, variables)
        if missing:
            self.log_message(
                f"Stylesheet '{name}' uses unknown variables: {', '.join(sorted(missing))}", logging.WARNING
            )
        return text

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
            self.log_message(f"Could not find path for the module '{module}'", logging.WARNING)
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
                self.log_message(f"Could not discover files of '{module}': {e}", logging.WARNING)
                continue
            self.log_message(f"Found {len(paths)} files in '{module}'")
            all_paths += paths
            for path in paths:
                mapping[path] = i
            directories = self._get_directories(i)
            all_directories += directories
            for directory in directories:
                directory_mapping[directory] = i
        # registered stylesheets stay watched, even when they do not belong to a module
        all_paths += [path for path in self.stylesheets if path not in mapping]
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
        """Rediscover changed directories, then reload all queued paths as one batch."""
        self._discover_pending_directories()
        paths = natsorted(self._pending_paths)
        self._pending_paths.clear()
        watched = set(self._watcher.files())
        to_reload: list[str] = []
        registered = set(self.stylesheets)
        for path in paths:
            if path not in self.path_to_index_map and path not in registered:
                # module was removed from the watch list while the change was pending
                continue
            if not Path(path).exists():
                self.log_message(f"'{path}' no longer exists - skipping")
                continue
            # editors that save by replacing the file cause the watcher to drop the path, so add it back
            if path not in watched:
                self._watcher.addPath(path)
            to_reload.append(path)
        self._reload_batch(to_reload)

    def _reload_batch(self, paths: list[str]) -> None:
        """Reload python files in import order, then stylesheets."""
        registered = set(self.stylesheets)
        python = [path for path in paths if path.endswith(".py") and path not in registered]
        for path in self._order_by_imports(python):
            self._reload_py(path)
        stylesheets = [path for path in paths if path.endswith(".qss") or path in registered]
        if stylesheets:
            self._reload_stylesheets(stylesheets)

    def _reload_stylesheets(self, paths: list[str]) -> None:
        """Re-apply registered stylesheets among `paths` and signal the change (`evt_stylesheet` only once)."""
        self.log_message(f"{', '.join(repr(Path(path).name) for path in paths)} changed")
        self._apply_stylesheets(paths)
        for path in paths:
            self.evt_stylesheet_changed.emit(path)
        self.evt_stylesheet.emit()

    def _order_by_imports(self, paths: list[str]) -> list[str]:
        """Order python files so that each module is reloaded after the modules (from `paths`) it imports.

        This matters when a module starts using a name that was just added to another module: reloading the
        importing module first would fail. Ties keep the natural sort order, as do import cycles.
        """
        paths = natsorted(set(paths))
        module_to_path: dict[str, str] = {}
        for path in paths:
            with suppress(ValueError):
                module_to_path[self.get_module_for_path(path)] = path

        dependencies: dict[str, set[str]] = {}
        dependents: dict[str, list[str]] = {path: [] for path in paths}
        for module, path in module_to_path.items():
            imported = get_imported_modules(path, module)
            dependencies[path] = {module_to_path[name] for name in imported if name in module_to_path} - {path}
            for dependency in dependencies[path]:
                dependents[dependency].append(path)

        position = {path: i for i, path in enumerate(paths)}
        remaining = {path: len(dependencies.get(path, ())) for path in paths}
        ready = [(position[path], path) for path, count in remaining.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while remaining:
            if not ready:
                # import cycle - continue with the first remaining file in natural order
                path = min(remaining, key=position.__getitem__)
                heapq.heappush(ready, (position[path], path))
            _, path = heapq.heappop(ready)
            if path not in remaining:
                continue
            del remaining[path]
            ordered.append(path)
            for dependent in dependents[path]:
                if dependent in remaining:
                    remaining[dependent] -= 1
                    if remaining[dependent] == 0:
                        heapq.heappush(ready, (position[dependent], dependent))
        return ordered

    def reload_path(self, path: str) -> ReloadResult | None:
        """Reload a python or stylesheet file immediately.

        Returns the result for python files, or None if the file is a stylesheet or its module was not reloaded
        (e.g. not imported yet).
        """
        registered = path in self.stylesheets
        if path.endswith(".py") and not registered:
            return self._reload_py(path)
        if path.endswith(".qss") or registered:
            self._reload_stylesheets([path])
        return None

    def reload_all_py(self) -> None:
        """Reload all watched python files, in import order."""
        for path in self._order_by_imports([path for path in self.files if path.endswith(".py")]):
            self._reload_py(path)

    def reload_stylesheets(self) -> None:
        """Re-apply registered stylesheets and ask listeners to re-apply theirs."""
        self.log_message("Reloading all stylesheet files...")
        self._apply_stylesheets()
        self.evt_stylesheet.emit()

    def _reload_py(self, path: str) -> ReloadResult | None:
        try:
            module = self.get_module_for_path(path)
        except ValueError as e:
            self.log_message(f"failed to reload '{path}' Error={e}...", logging.ERROR)
            return None
        mod = sys.modules.get(module)
        if mod is None:
            self.log_message(f"'{module}' has not been imported yet - skipping")
            return None
        reloader = Reload(mod)
        reloader.apply()
        error = reloader.error
        result = ReloadResult(
            module=module,
            path=path,
            changed=reloader.found_change,
            added=tuple(reloader.added),
            updated=tuple(reloader.updated),
            warnings=tuple(reloader.warnings),
            error=error,
            traceback="".join(traceback.format_exception(type(error), error, error.__traceback__)) if error else "",
        )
        for warning in result.warnings:
            self.log_message(f"'{module}': {warning}", logging.WARNING)
        if not result.ok:
            self.log_message(f"failed to reload '{module}' Error={result.summary()}", logging.ERROR)
            self.evt_reload_failed.emit(result)
            return result
        self.log_message(f"'{module}' reloaded: {result.summary()}")
        self.evt_pyfile.emit(module)
        self.evt_reloaded.emit(result)
        return result

    def log_message(self, msg: str, level: int = logging.INFO) -> None:
        """Timestamp `msg` and pass it to the logger, `log_func`, `messages` and `evt_message`."""
        msg = f"{datetime.now().strftime(TIME_FMT)} - {msg}"
        logger.debug(msg)
        self._messages.append((msg, level))
        if self.log_func is not None:
            self.log_func(msg)
        self.evt_message.emit(msg, level)
