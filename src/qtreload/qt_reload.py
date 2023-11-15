"""Hot-reload widget."""
from __future__ import annotations

import importlib
import typing as ty
from datetime import datetime
from logging import getLogger
from pathlib import Path

from qtpy.QtCore import QFileSystemWatcher, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import qthrottled

from qtreload.pydevd_reload import xreload
from qtreload.utilities import get_import_path, path_to_module

logger = getLogger(__name__)


TIME_FMT = "%Y-%m-%d %H:%M:%S"


class QtReloadWidget(QWidget):
    """Reload Widget."""

    evt_theme = Signal()

    def __init__(self, modules: ty.Iterable[str], parent=None, auto_connect: bool = True) -> None:
        super().__init__(parent=parent)
        # setup stylesheet
        self.setStyleSheet("""QtReloadWidget QTextEdit { border: 2px solid #ff0000; border-radius: 2px;}""")

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

        self._info_text = QTextEdit(self)
        self._info_text.setReadOnly(True)

        layout = QVBoxLayout()
        layout.addWidget(self._add_module_text)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._remove_btn)
        layout.addLayout(btn_layout)
        layout.addWidget(self._modules_list)

        main_layout = QHBoxLayout(self)
        main_layout.addLayout(layout)
        main_layout.addWidget(self._info_text, stretch=True)

        # setup modules
        paths = []
        for module in modules:
            path = get_import_path(module)
            if path:
                paths.append(path)
                self._modules_list.addItem(module)
                self.log_message(f"Watching for changes in '{path}'")
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
        for i, module_path in enumerate(self._module_paths):
            if module_path:
                paths = self._get_file_paths(module_path)
                all_paths += paths
                for _path in paths:
                    mapping[_path] = i
        self._set_paths(all_paths)
        self.path_to_index_map = mapping

    def _get_file_paths(self, path: Path):
        paths = []
        py = 0
        for new_path in path.glob("**/*.py"):
            # exclude __ini__ files since they won't be reloaded
            if new_path.name == "__init__.py":
                continue
            # exclude test files
            elif new_path.name.startswith("test_"):
                continue
            paths.append(str(new_path))
            py += 1
        # get list of qss files
        qss = 0
        for new_path in path.glob("**/*.qss"):
            paths.append(str(new_path))
            qss += 1
        paths = list(set(paths))
        self.log_message(f"Found {py} python files and {qss} qss files '{path.name}'")
        return paths

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
        except Exception as e:
            self.log_message(f"{now} - failed to reload '{path}' Error={e}...")

    def _reload_qss(self, path: str):
        self.evt_theme.emit()
        now = datetime.now().strftime(TIME_FMT)
        self.log_message(f"{now} - '{Path(path).name}' changed")

    def log_message(self, msg: str):
        """Log message."""
        self._info_text.append(msg)
        logger.debug(msg)
