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
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import qthrottled

from qtreload.pydevd_reload import xreload
from qtreload.utilities import get_import_path, get_module_paths, path_to_module

logger = getLogger(__name__)


TIME_FMT = "%Y-%m-%d %H:%M:%S"


class QtReloadWidget(QWidget):
    """Reload Widget."""

    evt_pyfile = Signal(str)
    evt_stylesheet = Signal()

    def __init__(
        self,
        modules: ty.Iterable[str],
        parent: QWidget | None = None,
        auto_connect: bool = True,
        py_pattern: tuple[str, ...] = ("**/*.py",),
        ignore_py_pattern=("**/__init__.py", "**/test_*.py"),
        stylesheet_pattern: tuple[str, ...] = ("**/*.qss",),
        log_func: ty.Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent=parent)
        # setup stylesheet
        self.setStyleSheet("""QtReloadWidget QTextEdit { border: 2px solid #ff0000; border-radius: 2px;}""")

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
        self._modules_list = QListWidget()
        self._modules_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self._add_btn = QPushButton("Add")
        self._add_btn.setToolTip("Add module to watch list. Module name is taken from the text field above.")
        self._add_btn.clicked.connect(self.on_add_module)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setToolTip("Remove selected modules from the watch list.")
        self._remove_btn.clicked.connect(self.on_remove_module)

        self._reload_py_btn = QPushButton("Reload python files")
        self._reload_py_btn.setToolTip(
            "Reload all python files. This can be fairly slow if there are a lot files to reload."
        )
        self._reload_py_btn.clicked.connect(self.on_reload_py_files)

        self._reload_qss_btn = QPushButton("Reload stylesheet files")
        self._reload_qss_btn.setToolTip("Reload all QSS files.")
        self._reload_qss_btn.clicked.connect(self.on_reload_stylesheet_files)

        self._info_text = QTextEdit(self)
        self._info_text.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self._add_module_text)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._remove_btn)
        layout.addLayout(btn_layout)
        layout.addWidget(self._modules_list)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._reload_py_btn)
        btn_layout.addWidget(self._reload_qss_btn)
        layout.addLayout(btn_layout)

        main_layout = QHBoxLayout(self)
        main_layout.addLayout(layout)
        main_layout.addWidget(self._info_text, stretch=True)

        # setup modules
        modules_, paths = [], []
        for module in modules:
            path = get_import_path(module)
            if path:
                modules_.append(module)
                paths.append(path)
                self._modules_list.addItem(module)
                self.log_message(f"Watching for changes in '{path}'")
        self._modules = modules_
        self._module_paths = paths
        self.path_to_index_map = {}
        if self._module_paths and auto_connect:
            self.setup_paths()

    def on_add_module(self):
        """Add new module to the list."""
        module = self._add_module_text.text()
        if not module:
            self.log_message(f"The specified module '{module}' does not exist.")
            return
        path = get_import_path(module)
        if not path:
            self.log_message(f"Could not find path for the module '{module}")
            return
        self._modules.append(module)
        self._module_paths.append(path)
        self._modules_list.addItem(module)
        self._add_module_text.clear()
        self.setup_paths(clear=True, connect=False)

    def on_remove_module(self):
        """Remove module(s) from the list."""
        items = self._modules_list.selectedItems()
        if not items:
            self.log_message("No modules selected.")
            return
        indices = [self._modules_list.row(item) for item in items]
        for index in sorted(indices, reverse=True):
            self._modules_list.takeItem(index)
            self._module_paths.pop(index)
        self.setup_paths(clear=True, connect=False)

    def setup_paths(self, clear: bool = False, connect: bool = True):
        """Setup paths."""
        if clear:
            self._remove_filenames()
        self._add_filenames()
        if connect:
            self._watcher.fileChanged.connect(self.on_reload_file)

    def _remove_filenames(self):
        """Clear existing filenames."""
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)
        directories = self._watcher.directories()
        if directories:
            self._watcher.removePaths(directories)
        self.log_message(f"Removed {len(files)} files and {len(directories)} directories from watcher.")

    def _add_filenames(self):
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
        )
        py = len(py_paths)
        qss = len(qss_paths)
        self.log_message(f"Found {py} python files and {qss} qss files '{module}'")
        paths = py_paths + qss_paths
        return [str(p) for p in paths]

    def _set_paths(self, paths: list[str]):
        self.log_message(f"Added {len(paths)} paths to watcher")
        if paths:
            self._watcher.addPaths(paths)

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

    def on_reload_stylesheet_files(self):
        self.log_message("Reloading all stylesheet files...")
        self.evt_stylesheet.emit()

    @qthrottled(timeout=500, leading=False)
    def on_reload_file(self, path: str):
        """Reload all modules."""
        self._reload_file(path)

    def _reload_file(self, path: str):
        if path.endswith(".py"):
            self._reload_py(path)
        elif path.endswith(".qss"):
            self._reload_qss(path)

    def _reload_py(self, path: str):
        now = datetime.now().strftime(TIME_FMT)
        try:
            module = path_to_module(path, self.get_module_path_for_path(path))
            res = xreload(importlib.import_module(module))
            self.log_message(f"{now} - '{module}' (changed={res})")
            self.evt_pyfile.emit(module)
        except Exception as e:
            self.log_message(f"{now} - failed to reload '{path}' Error={e}...")

    def _reload_qss(self, path: str):
        self.evt_stylesheet.emit()
        now = datetime.now().strftime(TIME_FMT)
        self.log_message(f"{now} - '{Path(path).name}' changed")

    def log_message(self, msg: str):
        """Log message."""
        with suppress(Exception):
            self._info_text.append(msg)
        logger.debug(msg)
        self.log_func(msg)


class QDevPopup(QDialog):
    def __init__(self, parent: QWidget, modules: list[str]):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(title_layout)
        layout.addWidget(self.qdev, stretch=True)
