"""Hot-reload widget."""

from __future__ import annotations

import html
import logging
import typing as ty
from contextlib import suppress
from pathlib import Path

from qtpy.QtCore import QModelIndex, Qt, Signal
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

from qtreload.reloader import (
    MAX_MESSAGES,
    PY_IGNORE_PATTERN,
    PY_PATTERN,
    RELOAD_DELAY_MS,
    STYLESHEET_PATTERN,
    TIME_FMT,
    HotReloader,
    ReloadResult,
)

# colors of log messages and the status line - readable on both light and dark backgrounds
LEVEL_COLORS = {logging.WARNING: "#e69500", logging.ERROR: "#d9534f"}
SUCCESS_COLOR = "#3c9d3c"

__all__ = [
    "PY_IGNORE_PATTERN",
    "PY_PATTERN",
    "RELOAD_DELAY_MS",
    "STYLESHEET_PATTERN",
    "TIME_FMT",
    "QtDevPopup",
    "QtReloadWidget",
    "get_main_window",
]


def get_main_window() -> QMainWindow | None:
    """Get main window."""
    app = QApplication.instance()
    if app:
        for i in app.topLevelWidgets():
            if isinstance(i, QMainWindow):  # pragma: no cover
                return i
    return None


class QtReloadWidget(QWidget):
    """Widget to manage hot-reloading of modules.

    All watching and reloading is done by the `HotReloader` available as `reloader`, this widget only displays
    and edits its state. See `HotReloader` for a description of the parameters.
    """

    evt_pyfile = Signal(str)
    evt_stylesheet = Signal()
    evt_stylesheet_changed = Signal(str)

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
        self.widgets: list[QWidget] = []

        self._add_module_text = QLineEdit(self)
        self._add_module_text.returnPressed.connect(self.on_add_module)

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
        self._log_edit.document().setMaximumBlockCount(MAX_MESSAGES)

        self._status_label = QLabel("No reloads yet", self)
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._file_filter = QLineEdit(self)
        self._file_filter.setPlaceholderText("Filter files...")
        self._file_filter.setToolTip("Start typing to filter files in the list...")
        self._file_filter.textChanged.connect(self.on_filter_changed)
        self._file_filter.editingFinished.connect(self.on_filter_changed)

        self._files_list = QListWidget(self)
        self._files_list.doubleClicked.connect(self.on_double_click)

        files_tab = QWidget()
        files_layout = QVBoxLayout(files_tab)
        files_layout.addWidget(self._file_filter)
        files_layout.addWidget(self._files_list)

        tabs = QTabWidget(self)
        tabs.addTab(self._log_edit, "Log")
        tabs.addTab(files_tab, "Files")

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
        self.side_layout = layout

        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.addLayout(layout)
        right_layout = QVBoxLayout()
        right_layout.setSpacing(2)
        right_layout.addWidget(self._status_label)
        right_layout.addWidget(tabs, stretch=True)
        main_layout.addLayout(right_layout, stretch=True)

        self.reloader = HotReloader(
            modules,
            parent=self,
            auto_connect=auto_connect,
            py_pattern=py_pattern,
            ignore_py_pattern=ignore_py_pattern,
            stylesheet_pattern=stylesheet_pattern,
            log_func=log_func,
        )
        self.reloader.evt_pyfile.connect(self.evt_pyfile)
        self.reloader.evt_stylesheet.connect(self.evt_stylesheet)
        self.reloader.evt_stylesheet_changed.connect(self.evt_stylesheet_changed)
        self.reloader.evt_reloaded.connect(self._on_reload_result)
        self.reloader.evt_reload_failed.connect(self._on_reload_result)
        # show what was logged while the reloader was set up, then follow new messages
        for msg, level in self.reloader.messages:
            self._on_message(msg, level)
        self.reloader.evt_message.connect(self._on_message)
        self.reloader.evt_watchlist_changed.connect(self._on_watchlist_changed)
        self._on_watchlist_changed()

    # Reloader state, kept for backwards compatibility

    @property
    def log_func(self) -> ty.Callable[[str], None] | None:
        """Function called with every log message."""
        return self.reloader.log_func

    @log_func.setter
    def log_func(self, value: ty.Callable[[str], None] | None) -> None:
        self.reloader.log_func = value

    @property
    def py_pattern(self) -> tuple[str, ...]:
        """Python file patterns."""
        return self.reloader.py_pattern

    @py_pattern.setter
    def py_pattern(self, value: tuple[str, ...]) -> None:
        self.reloader.py_pattern = value

    @property
    def ignore_py_pattern(self) -> tuple[str, ...]:
        """Ignored python file patterns."""
        return self.reloader.ignore_py_pattern

    @ignore_py_pattern.setter
    def ignore_py_pattern(self, value: tuple[str, ...]) -> None:
        self.reloader.ignore_py_pattern = value

    @property
    def stylesheet_pattern(self) -> tuple[str, ...]:
        """Stylesheet file patterns."""
        return self.reloader.stylesheet_pattern

    @stylesheet_pattern.setter
    def stylesheet_pattern(self, value: tuple[str, ...]) -> None:
        self.reloader.stylesheet_pattern = value

    @property
    def path_to_index_map(self) -> dict[str, int]:
        """Mapping of watched file path to the index of its module."""
        return self.reloader.path_to_index_map

    def replace_modules(self, modules: ty.Iterable[str]) -> None:
        """Replace the watched module list and refresh watched paths."""
        self.reloader.replace_modules(modules)

    def setup_paths(self, clear: bool = False, connect: bool = True) -> None:
        """Discover and watch files, optionally clearing the previous ones and connecting the watcher."""
        self.reloader.setup_paths(clear=clear, connect=connect)

    def get_module_path_for_path(self, path: str) -> Path:
        """Return the import path of the watched module that `path` belongs to."""
        return self.reloader.get_module_path_for_path(path)

    def get_module_for_path(self, path: str) -> str:
        """Map a watched file path to its fully qualified module name."""
        return self.reloader.get_module_for_path(path)

    def on_reload_file(self, path: str) -> None:
        """Queue `path` for reloading once file changes settle."""
        self.reloader.on_reload_file(path)

    def log_message(self, msg: str, level: int = logging.INFO) -> None:
        """Log message."""
        self.reloader.log_message(msg, level)

    # UI

    def register_widget(self, widget: QWidget) -> None:
        """Register a QWidget as a child widget."""
        self.widgets.append(widget)

    def _on_message(self, msg: str, level: int) -> None:
        """Show a log message from the reloader, colored by its level."""
        color = LEVEL_COLORS.get(level)
        style = f' style="color: {color}"' if color else ""
        with suppress(RuntimeError):
            self._log_edit.append(f"<span{style}>{html.escape(msg)}</span>")

    def _on_reload_result(self, result: ReloadResult) -> None:
        """Show the outcome of the last reload."""
        status = "Reloaded" if result.ok else "Failed to reload"
        color = SUCCESS_COLOR if result.ok else LEVEL_COLORS[logging.ERROR]
        self._status_label.setText(f"{status} '{result.module}': {result.summary()}")
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setToolTip(result.traceback or result.summary(max_names=50))

    def _on_watchlist_changed(self) -> None:
        """Show the reloader's modules, patterns and files."""
        self._modules_list.clear()
        self._modules_list.addItems(list(self.reloader.modules))
        self._files_list.clear()
        self._files_list.addItems(self.reloader.files)
        self.on_filter_changed()
        self._py_pattern_text.setText(", ".join(self.reloader.py_pattern))
        self._py_ignore_pattern_text.setText(", ".join(self.reloader.ignore_py_pattern))
        self._stylesheet_pattern_text.setText(", ".join(self.reloader.stylesheet_pattern))

    def on_double_click(self, index: QModelIndex) -> None:
        """Reload the selected file."""
        item = self._files_list.item(index.row())
        self.reloader.reload_path(item.text())

    def on_py_pattern_changed(self) -> None:
        """Update python patterns from the text fields."""
        self.reloader.set_patterns(
            py_pattern=_split_patterns(self._py_pattern_text.text()),
            ignore_py_pattern=_split_patterns(self._py_ignore_pattern_text.text()),
        )

    def on_stylesheet_pattern_changed(self) -> None:
        """Update stylesheet patterns from the text field."""
        self.reloader.set_patterns(stylesheet_pattern=_split_patterns(self._stylesheet_pattern_text.text()))

    def on_add_module(self) -> None:
        """Add the module typed in the text field."""
        module = self._add_module_text.text().strip()
        if not module:
            self.log_message("Please specify the name of the module to add.")
            return
        if self.reloader.add_module(module):
            self._add_module_text.clear()

    def on_remove_module(self) -> None:
        """Remove the selected module(s)."""
        items = self._modules_list.selectedItems()
        if not items:
            self.log_message("No modules selected.")
            return
        self.reloader.remove_modules([item.text() for item in items])

    def on_refresh_filelist(self) -> None:
        """Rediscover files of all modules."""
        self.reloader.refresh()

    def on_filter_changed(self, text: str | None = None) -> None:
        """Filter files in the list."""
        text = self._file_filter.text().strip()
        for row in range(self._files_list.count()):
            item = self._files_list.item(row)
            item.setHidden(text not in item.text() if text else False)

    def on_reload_py_files(self) -> None:
        """Reload all python files."""
        self.reloader.reload_all_py()

    def on_reload_stylesheet_files(self) -> None:
        """Reload all stylesheet files."""
        self.reloader.reload_stylesheets()

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
        for widget in self.widgets:
            with suppress(RuntimeError):
                stylesheet = widget.styleSheet()
                if state:
                    stylesheet += "\n" + tmp_stylesheet
                else:
                    stylesheet = stylesheet.replace(tmp_stylesheet, "")
                widget.setStyleSheet(stylesheet)
        self.log_message(f"Toggled widget borders (state={state})")


def _split_patterns(text: str) -> tuple[str, ...]:
    """Split comma-separated patterns, dropping whitespace and empty entries."""
    return tuple(pattern.strip() for pattern in text.split(",") if pattern.strip())


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
