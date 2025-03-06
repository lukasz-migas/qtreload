"""Hot-reload widget."""

from __future__ import annotations

import importlib
import typing as ty
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from pathlib import Path

from qtpy.QtCore import QFileSystemWatcher, Qt, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import qthrottled

from qtreload.pydevd_reload import xreload
from qtreload.utilities import get_import_path, get_module_paths, path_to_module

logger = getLogger(__name__)


TIME_FMT = "%Y-%m-%d %H:%M:%S"

PY_PATTERN = ("**/*.py",)
PY_IGNORE_PATTERN = ("**/__init__.py", "**/test_*.py")
STYLESHEET_PATTERN = ("**/*.qss",)


def get_main_window() -> QMainWindow | None:
    """Get main window."""
    app = QApplication.instance()
    if app:
        for i in app.topLevelWidgets():
            if isinstance(i, QMainWindow):  # pragma: no cover
                return i
    return None


class QtReloadWidget(QWidget):
    """Reload Widget."""

    evt_pyfile = Signal(str)
    evt_stylesheet = Signal()

    def __init__(
        self,
        modules: ty.Iterable[str],
        parent: QWidget | None = None,
        auto_connect: bool = True,
        py_pattern: tuple[str, ...] = PY_PATTERN,
        ignore_py_pattern: tuple[str, ...] = PY_IGNORE_PATTERN,
        stylesheet_pattern: tuple[str, ...] = STYLESHEET_PATTERN,
        log_func: ty.Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent=parent)

        if log_func is None:

            def log_func(x):
                return None

        self.log_func = log_func
        # pattern information
        self.py_pattern = py_pattern
        self.ignore_py_pattern = ignore_py_pattern
        self.stylesheet_pattern = stylesheet_pattern

        # setup file watcher
        self._watcher = QFileSystemWatcher()

        self._add_module_text = QLineEdit(self)
        self._add_module_text.editingFinished.connect(self.on_add_module)

        self._add_btn = QPushButton("Add")
        self._add_btn.setToolTip("Add module to watch list. Module name is taken from the text field above.")
        self._add_btn.clicked.connect(self.on_add_module)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setToolTip("Remove selected modules from the watch list.")
        self._remove_btn.clicked.connect(self.on_remove_module)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setToolTip("Reload list of files for all modules.")
        self._refresh_btn.clicked.connect(self.on_refresh_filelist)

        self._modules_list = QListWidget()
        self._modules_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self._py_pattern_text = QLineEdit(self)
        self._py_pattern_text.setText(", ".join(py_pattern))
        self._py_pattern_text.setToolTip(
            "Python file patterns to watch for changes. Use comma to separate patterns. Spaces will be stripped."
        )
        self._py_pattern_text.editingFinished.connect(self.on_py_pattern_changed)

        self._py_ignore_pattern_text = QLineEdit(self)
        self._py_ignore_pattern_text.setText(", ".join(ignore_py_pattern))
        self._py_ignore_pattern_text.setToolTip(
            "Python file patterns to ignore during discovery. Use comma to separate. Spaces will be stripped."
        )
        self._py_ignore_pattern_text.editingFinished.connect(self.on_py_pattern_changed)

        self._stylesheet_pattern_text = QLineEdit(self)
        self._stylesheet_pattern_text.setText(", ".join(stylesheet_pattern))
        self._stylesheet_pattern_text.setToolTip(
            "Stylesheet file patterns to watch for changes. Use comma to separate. Spaces will be stripped."
        )
        self._stylesheet_pattern_text.editingFinished.connect(self.on_stylesheet_pattern_changed)

        self._reload_py_btn = QPushButton("Reload python files")
        self._reload_py_btn.setToolTip(
            "Reload all python files. This can be fairly slow if there are a lot files to reload."
        )
        self._reload_py_btn.clicked.connect(self.on_reload_py_files)

        self._reload_qss_btn = QPushButton("Reload stylesheet files")
        self._reload_qss_btn.setToolTip("Reload all QSS files.")
        self._reload_qss_btn.clicked.connect(self.on_reload_stylesheet_files)

        self._enable_widget_borders = QCheckBox("Show widget borders")
        self._enable_widget_borders.setToolTip("Show borders around each widget in the app.")
        self._enable_widget_borders.stateChanged.connect(self.on_toggle_widget_borders)

        self._log_edit = QTextEdit(self)
        self._log_edit.setReadOnly(True)

        self._files_list = QListWidget(self)

        tabs = QTabWidget(self)
        tabs.addTab(self._log_edit, "Log")
        tabs.addTab(self._files_list, "Files")

        add_btn_layout = QHBoxLayout()
        add_btn_layout.setSpacing(2)
        add_btn_layout.addWidget(self._add_btn)
        add_btn_layout.addWidget(self._remove_btn)
        add_btn_layout.addWidget(self._refresh_btn)

        reload_btn_layout = QHBoxLayout()
        reload_btn_layout.setSpacing(2)
        reload_btn_layout.addWidget(self._reload_py_btn)
        reload_btn_layout.addWidget(self._reload_qss_btn)

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.addWidget(QLabel("Modules"))
        layout.addWidget(self._add_module_text)
        layout.addLayout(add_btn_layout)
        layout.addWidget(self._modules_list)
        layout.addWidget(self._enable_widget_borders)

        layout.addWidget(QLabel("Python pattern (comma separated)"))
        layout.addWidget(self._py_pattern_text)
        layout.addWidget(QLabel("Python ignore pattern (comma separated)"))
        layout.addWidget(self._py_ignore_pattern_text)
        layout.addWidget(QLabel("Stylesheet pattern (comma separated)"))
        layout.addWidget(self._stylesheet_pattern_text)
        layout.addLayout(reload_btn_layout)

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(2)
        main_layout.addLayout(layout)
        main_layout.addWidget(tabs, stretch=True)

        # setup modules
        modules_, paths = [], []
        for module in modules:
            if module in modules_:
                continue
            path = get_import_path(module)
            if path:
                modules_.append(module)
                paths.append(path)
                self._modules_list.addItem(module)
                self.log_message(f"Watching for changes in '{path}'")
        self._modules = modules_
        self._module_paths = paths
        self.path_to_index_map: dict[Path, int] = {}
        if self._module_paths and auto_connect:
            self.setup_paths()

    def on_py_pattern_changed(self) -> None:
        """Update python pattern."""
        py_pattern = tuple(self._py_pattern_text.text().split(","))
        self.py_pattern = tuple(py.strip() for py in py_pattern)
        ignore_py_pattern = tuple(self._py_ignore_pattern_text.text().split(","))
        self.ignore_py_pattern = tuple(py.strip() for py in ignore_py_pattern)
        self.on_refresh_filelist()

    def on_stylesheet_pattern_changed(self) -> None:
        """Update stylesheet pattern."""
        stylesheet_pattern = tuple(self._stylesheet_pattern_text.text().split(","))
        self.stylesheet_pattern = tuple(py.strip() for py in stylesheet_pattern)
        self.on_refresh_filelist()

    def on_add_module(self) -> None:
        """Add new module to the list."""
        module = self._add_module_text.text()
        if not module:
            self.log_message(f"The specified module '{module}' does not exist.")
            return
        if module in self._modules:
            self.log_message(f"The module '{module}' is already in the list.")
            return
        path = get_import_path(module)
        if not path:
            self.log_message(f"Could not find path for the module '{module}")
            return
        self.log_message(f"Watching for changes in '{path}'")
        self._modules.append(module)
        self._module_paths.append(path)
        self._modules_list.addItem(module)
        self._add_module_text.clear()
        self.on_refresh_filelist()

    def on_remove_module(self) -> None:
        """Remove module(s) from the list."""
        items = self._modules_list.selectedItems()
        if not items:
            self.log_message("No modules selected.")
            return
        indices = [self._modules_list.row(item) for item in items]
        modules = [item.text() for item in items]
        for index in sorted(indices, reverse=True):
            self._modules_list.takeItem(index)
            self._module_paths.pop(index)
        for module in modules:
            self._modules.remove(module)
        self.on_refresh_filelist()

    def on_refresh_filelist(self) -> None:
        """Refresh file list."""
        self.setup_paths(clear=True, connect=False)

    def setup_paths(self, clear: bool = False, connect: bool = True) -> None:
        """Setup paths."""
        if clear:
            self._remove_filenames()
        self._add_filenames()
        if connect:
            self._watcher.fileChanged.connect(self.on_reload_file)

    def _remove_filenames(self) -> None:
        """Clear existing filenames."""
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)
        directories = self._watcher.directories()
        if directories:
            self._watcher.removePaths(directories)
        self.log_message(f"Removed {len(files)} files and {len(directories)} directories from watcher.")

    def _add_filenames(self) -> None:
        """Set paths."""
        all_paths = []
        mapping = {}
        for i, module in enumerate(self._modules):
            module_path = get_import_path(module)
            if module_path:
                paths = self._get_file_paths(module)
                all_paths += paths
                for _path in paths:
                    mapping[_path] = i
        self._set_paths(all_paths)
        self.path_to_index_map = mapping

    def _get_file_paths(self, module: str) -> list[str]:
        """Get file paths."""
        py_paths, qss_paths = get_module_paths(
            module,
            py_pattern=self.py_pattern,
            ignore_py_pattern=self.ignore_py_pattern,
            stylesheet_pattern=self.stylesheet_pattern,
            log_func=self.log_func,
        )
        py = len(py_paths)
        qss = len(qss_paths)
        self.log_message(f"Found {py} python files and {qss} qss files '{module}'")
        paths = py_paths + qss_paths
        return [str(p) for p in paths]

    def _set_paths(self, paths: list[str]) -> None:
        self.log_message(f"Added {len(paths)} paths to watcher")
        if paths:
            self._watcher.addPaths(paths)
        self._files_list.clear()
        for path in paths:
            self._files_list.addItem(path)

    def get_module_path_for_path(self, path: str) -> Path:
        """Map path to module."""
        index = self.path_to_index_map.get(path, None)
        if index is None:
            raise ValueError("Path not found in module paths")
        return self._module_paths[index]

    def on_reload_py_files(self) -> None:
        """Reload python files."""
        for path in self._watcher.files():
            if path.endswith(".py"):
                self._reload_py(path)

    def on_reload_stylesheet_files(self) -> None:
        """Reload all stylesheet files."""
        self.log_message("Reloading all stylesheet files...")
        self.evt_stylesheet.emit()

    def on_toggle_widget_borders(self, state: int) -> None:
        """Toggle widget borders."""
        window = get_main_window() or self.parent() or self
        if not window:
            return
        tmp_stylesheet = "QWidget { border: 1px solid #ff0000;}"
        stylesheet = window.styleSheet()
        if state:
            stylesheet += "\n" + tmp_stylesheet
        else:
            stylesheet = stylesheet.replace(tmp_stylesheet, "")
        window.setStyleSheet(stylesheet)
        self.log_message(f"Toggled widget borders (state={state})")

    @qthrottled(timeout=500, leading=False)
    def on_reload_file(self, path: str) -> None:
        """Reload all modules."""
        self._reload_file(path)

    def _reload_file(self, path: str) -> None:
        if path.endswith(".py"):
            self._reload_py(path)
        elif path.endswith(".qss"):
            self._reload_qss(path)

    def _reload_py(self, path: str) -> None:
        try:
            module = path_to_module(path, self.get_module_path_for_path(path))
            res = xreload(importlib.import_module(module))
            self.log_message(f"'{module}' (changed={res})")
            self.evt_pyfile.emit(module)
        except Exception as e:
            self.log_message(f"failed to reload '{path}' Error={e}...")

    def _reload_qss(self, path: str) -> None:
        self.evt_stylesheet.emit()
        self.log_message(f"'{Path(path).name}' changed")

    def log_message(self, msg: str) -> None:
        """Log message."""
        now = datetime.now().strftime(TIME_FMT)
        msg = f"{now} - {msg}"
        with suppress(Exception):
            self._log_edit.append(msg)
        logger.debug(msg)
        self.log_func(msg)


class QtDevPopup(QDialog):
    """Popup dialog."""

    def __init__(self, parent: QWidget, modules: list[str]):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumWidth(800)

        self.modules = modules

        self.qdev = QtReloadWidget(self.modules, self)

        title = QLabel()
        title.setText("Developer tools")
        close_btn = QPushButton()
        close_btn.setText("Hide")
        close_btn.clicked.connect(self.hide)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(2, 2, 2, 2)
        title_layout.addWidget(title, stretch=True)
        title_layout.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(title_layout)
        layout.addWidget(self.qdev, stretch=True)


if __name__ == "__main__":  # pragma: no cover
    import sys

    app = QApplication([])
    dlg = QtDevPopup(None, ["qtreload"])
    dlg.show()
    sys.exit(app.exec_())
