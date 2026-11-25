"""Inspect widgets of the running application and open their source code."""

from __future__ import annotations

import inspect
import logging
import os
import shlex
import typing as ty
from dataclasses import dataclass
from pathlib import Path

from qtpy.QtCore import QEvent, QObject, QPoint, QProcess, QRect, Qt, QTimer, QUrl, Signal
from qtpy.QtGui import QColor, QCursor, QDesktopServices, QPainter, QPen
from qtpy.QtWidgets import QApplication, QWidget

from qtreload.live import is_alive

__all__ = [
    "EDITOR_ENV_VARIABLE",
    "HighlightOverlay",
    "WidgetInfo",
    "WidgetInspector",
    "describe_widget",
    "find_source",
    "open_in_editor",
]

logger = logging.getLogger(__name__)

# environment variable with the command used to open files, e.g. "pycharm --line {line} {path}"
EDITOR_ENV_VARIABLE = "QTRELOAD_EDITOR"
# modules of Qt bindings, whose classes have no python source
QT_MODULE_PREFIXES = ("PySide2", "PySide6", "PyQt5", "PyQt6", "shiboken2", "shiboken6", "sip", "builtins")
HIGHLIGHT_COLOR = QColor(255, 0, 0)
# how often the widget under the cursor is checked while picking
PICK_INTERVAL_MS = 50


@dataclass(frozen=True)
class WidgetInfo:
    """Description of a widget.

    Attributes
    ----------
    class_name : str
        Qualified name of the widget's class.
    module : str
        Module of the widget's class.
    source_file : str, optional
        File defining the first python (not Qt) class in the widget's class hierarchy.
    source_line : int, optional
        Line of that class definition.
    object_name : str
        Qt object name.
    geometry : tuple[int, int, int, int]
        Position and size (x, y, width, height) relative to the parent.
    visible : bool
        Whether the widget is visible.
    enabled : bool
        Whether the widget is enabled.
    parents : tuple[str, ...]
        Class names of the parents, closest first.
    stylesheet : str
        Stylesheet set on the widget itself.
    """

    class_name: str
    module: str
    source_file: str | None
    source_line: int | None
    object_name: str
    geometry: tuple[int, int, int, int]
    visible: bool
    enabled: bool
    parents: tuple[str, ...]
    stylesheet: str

    def format(self) -> str:
        """Human readable, multi-line description."""
        source = f"{self.source_file}:{self.source_line}" if self.source_file else "-"
        x, y, width, height = self.geometry
        lines = [
            f"Class:       {self.class_name}",
            f"Module:      {self.module}",
            f"Source:      {source}",
            f"Object name: {self.object_name or '-'}",
            f"Geometry:    x={x}, y={y}, width={width}, height={height}",
            f"Visible:     {self.visible}",
            f"Enabled:     {self.enabled}",
            f"Parents:     {' > '.join(self.parents) or '-'}",
            "Stylesheet:",
            self.stylesheet or "-",
        ]
        return "\n".join(lines)


def find_source(cls: type) -> tuple[str, int] | None:
    """Return (file, line) of the first python class in the hierarchy of `cls`, skipping Qt classes."""
    for klass in cls.__mro__:
        if klass.__module__.startswith(QT_MODULE_PREFIXES):
            continue
        try:
            path = inspect.getsourcefile(klass)
            _, line = inspect.getsourcelines(klass)
        except (OSError, TypeError):
            continue
        if path:
            return path, line
    return None


def describe_widget(widget: QWidget) -> WidgetInfo:
    """Describe `widget`, including where its class is defined."""
    cls = type(widget)
    source = find_source(cls)
    parents = []
    parent = widget.parentWidget()
    while parent is not None:
        parents.append(type(parent).__qualname__)
        parent = parent.parentWidget()
    geometry = widget.geometry()
    return WidgetInfo(
        class_name=cls.__qualname__,
        module=cls.__module__,
        source_file=source[0] if source else None,
        source_line=source[1] if source else None,
        object_name=widget.objectName(),
        geometry=(geometry.x(), geometry.y(), geometry.width(), geometry.height()),
        visible=widget.isVisible(),
        enabled=widget.isEnabled(),
        parents=tuple(parents),
        stylesheet=widget.styleSheet(),
    )


def open_in_editor(path: str | Path, line: int | None = None, command: str | None = None) -> bool:
    """Open `path` (at `line`) in an editor. Returns True if the editor was started.

    Parameters
    ----------
    path : str | Path
        File to open.
    line : int, optional
        Line to go to, if the editor command supports it.
    command : str, optional
        Command template with `{path}` and `{line}` placeholders, e.g. "pycharm --line {line} {path}" or
        "code -g {path}:{line}". Defaults to the `QTRELOAD_EDITOR` environment variable, and to the application
        associated with the file type (without line) if that is not set either.
    """
    command = command or os.environ.get(EDITOR_ENV_VARIABLE)
    if not command:
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    try:
        arguments = [part.format(path=str(path), line=line or 1) for part in shlex.split(command)]
    except (ValueError, KeyError, IndexError) as e:
        logger.warning("Invalid editor command '%s': %s", command, e)
        return False
    if not arguments:
        return False
    # start the editor as a separate process, which keeps running after the application exits
    result = QProcess.startDetached(arguments[0], arguments[1:])
    started = bool(result[0] if isinstance(result, tuple) else result)
    if not started:
        logger.warning("Could not start the editor with '%s'", command)
    return started


class HighlightOverlay(QWidget):
    """Red frame drawn over another widget, which does not receive mouse events."""

    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setObjectName("qtreload_highlight")
        self._target: QWidget | None = None

    @property
    def target(self) -> QWidget | None:
        """The highlighted widget."""
        if self._target is not None and not is_alive(self._target):
            self._target = None
        return self._target

    def highlight(self, widget: QWidget | None) -> None:
        """Draw the frame over `widget`, or hide it if None."""
        self._target = widget
        if widget is None or not is_alive(widget) or widget.window() is None:
            self.hide()
            return
        window = widget.window()
        if self.parentWidget() is not window:
            self.setParent(window)
        top_left = widget.mapTo(window, QPoint(0, 0))
        self.setGeometry(QRect(top_left, widget.size()))
        self.show()
        self.raise_()

    def paintEvent(self, event: ty.Any) -> None:
        """Draw the frame."""
        painter = QPainter(self)
        pen = QPen(HIGHLIGHT_COLOR)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        painter.end()


class WidgetInspector(QObject):
    """Pick a widget of the application with the mouse.

    After `start`, the widget under the cursor is highlighted and `evt_hovered` is emitted when it changes. A click
    selects it (the click does not reach the widget), emits `evt_selected` and stops picking. Escape stops picking
    without selection.

    Parameters
    ----------
    parent : QObject, optional
        Qt parent.
    exclude : QWidget, optional
        Widget (with its children) that cannot be picked, e.g. the inspector's own user interface.
    """

    evt_hovered = Signal(object)
    evt_selected = Signal(object)
    evt_active_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None, exclude: QWidget | None = None) -> None:
        super().__init__(parent)
        self.exclude = exclude
        self._overlay = HighlightOverlay()
        self._active = False
        self._hovered: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(PICK_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def overlay(self) -> HighlightOverlay:
        """The highlight frame, recreated if it was deleted together with the window it was drawn on."""
        if not is_alive(self._overlay):
            self._overlay = HighlightOverlay()
        return self._overlay

    @property
    def active(self) -> bool:
        """Whether a widget is being picked."""
        return self._active

    def start(self) -> None:
        """Start picking."""
        if self._active:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._active = True
        self._timer.start()
        self.evt_active_changed.emit(True)

    def stop(self) -> None:
        """Stop picking. The highlight of the selected widget (if any) is kept."""
        if not self._active:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._active = False
        self._timer.stop()
        self._hovered = None
        self.evt_active_changed.emit(False)

    def hover(self, widget: QWidget | None) -> None:
        """Highlight `widget` as the one under the cursor."""
        widget = self._pickable(widget)
        if widget is self._hovered:
            return
        self._hovered = widget
        self.overlay.highlight(widget)
        if widget is not None:
            self.evt_hovered.emit(widget)

    def select(self, widget: QWidget | None) -> None:
        """Select `widget`, highlight it and stop picking."""
        widget = self._pickable(widget)
        self.stop()
        self.overlay.highlight(widget)
        if widget is not None:
            self.evt_selected.emit(widget)

    def _pickable(self, widget: QWidget | None) -> QWidget | None:
        """Return `widget` unless it is excluded or part of the overlay."""
        if widget is None or not is_alive(widget) or widget is self._overlay:
            return None
        if self.exclude is not None and is_alive(self.exclude):
            if widget is self.exclude or self.exclude.isAncestorOf(widget):
                return None
        return widget

    def _poll(self) -> None:
        self.hover(QApplication.widgetAt(QCursor.pos()))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Select clicked widgets and stop on Escape while picking."""
        if not self._active:
            return False
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and isinstance(obj, QWidget):
            target = self._pickable(obj)
            if target is not None:
                self.select(target)
                return True
        elif event_type in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            return isinstance(obj, QWidget) and self._pickable(obj) is not None
        elif event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.stop()
            self.overlay.highlight(None)
            return True
        return False
