"""Rebuild widgets in place when their code is reloaded."""

from __future__ import annotations

import logging
import typing as ty
from contextlib import suppress

from qtpy.QtCore import QObject, Qt, Signal
from qtpy.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

if ty.TYPE_CHECKING:
    from qtreload.reloader import HotReloader, ReloadResult

__all__ = ["LiveWidget", "is_alive", "replace_widget"]

logger = logging.getLogger(__name__)


def is_alive(widget: QObject) -> bool:
    """Return False if the C++ object of `widget` was deleted."""
    try:
        widget.objectName()
    except RuntimeError:
        return False
    return True


def replace_widget(old: QWidget, new: QWidget) -> None:
    """Put `new` where `old` is and schedule `old` for deletion.

    Supported places are layouts (including nested ones), splitters, tab widgets, stacked widgets, dock widgets,
    scroll areas, the central widget of a main window and top-level windows (the new window gets the geometry of the
    old one). Elsewhere, `new` gets the parent and geometry of `old`. Visibility is kept.
    """
    parent = old.parentWidget()
    # widgets added to a visible parent are hidden until Qt shows them, so only count explicit hiding
    hidden = old.isHidden() and old.testAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide)

    if parent is None:
        new.setGeometry(old.geometry())
        if old.isVisible():
            # show the new window before closing the old one, so the application does not quit
            new.show()
        old.close()
    else:
        _replace_child(parent, old, new)
        new.setVisible(not hidden)
    old.hide()
    with suppress(RuntimeError):
        old.deleteLater()


def _replace_child(parent: QWidget, old: QWidget, new: QWidget) -> None:
    """Put `new` in place of `old`, which is a child of `parent`."""
    container = parent.parentWidget()
    if isinstance(parent, QDockWidget) and parent.widget() is old:
        parent.setWidget(new)
    elif isinstance(parent, QSplitter):
        parent.replaceWidget(parent.indexOf(old), new)
    elif isinstance(parent, QStackedWidget) and isinstance(container, QTabWidget) and container.indexOf(old) >= 0:
        index = container.indexOf(old)
        is_current = container.currentIndex() == index
        text, icon, tooltip = container.tabText(index), container.tabIcon(index), container.tabToolTip(index)
        container.removeTab(index)
        container.insertTab(index, new, icon, text)
        container.setTabToolTip(index, tooltip)
        if is_current:
            container.setCurrentIndex(index)
    elif isinstance(parent, QStackedWidget):
        index = parent.indexOf(old)
        is_current = parent.currentWidget() is old
        parent.removeWidget(old)
        parent.insertWidget(index, new)
        if is_current:
            parent.setCurrentWidget(new)
    elif isinstance(container, QScrollArea) and container.widget() is old:
        container.takeWidget()
        container.setWidget(new)
    elif isinstance(parent, QMainWindow) and parent.centralWidget() is old:
        parent.takeCentralWidget()
        parent.setCentralWidget(new)
    elif parent.layout() is not None and parent.layout().replaceWidget(old, new) is not None:
        pass
    else:
        new.setParent(parent)
        new.setGeometry(old.geometry())


class LiveWidget(QObject):
    """Handle of a widget that is rebuilt by its factory when its code is reloaded.

    Create it with `HotReloader.register_factory`. The widget is rebuilt after a batch of reloads in which one of
    its modules changed and none of them failed. The new widget is put where the old one was (see
    `replace_widget`). While the factory runs, `widget` is still the old instance, so its state can be copied.

    Parameters
    ----------
    reloader : HotReloader
        Reloader whose reloads trigger rebuilds. It is also the Qt parent.
    factory : Callable[[], QWidget]
        Function creating the widget.
    widget : QWidget, optional
        Current instance, created with `factory` if not given.
    modules : Iterable[str]
        Additional modules or packages whose changes rebuild the widget. The module of the widget's class and of the
        factory are always included.
    """

    # emitted with the new widget after it replaced the old one
    evt_rebuilt = Signal(object)

    def __init__(
        self,
        reloader: HotReloader,
        factory: ty.Callable[[], QWidget],
        widget: QWidget | None = None,
        modules: ty.Iterable[str] = (),
    ) -> None:
        super().__init__(reloader)
        self._reloader = reloader
        self._factory = factory
        self._widget = widget if widget is not None else factory()
        defaults = (type(self._widget).__module__, getattr(factory, "__module__", None))
        self.modules = tuple(dict.fromkeys(name for name in (*modules, *defaults) if name))
        reloader.evt_batch_reloaded.connect(self._on_batch_reloaded)

    @property
    def widget(self) -> QWidget:
        """The current instance."""
        return self._widget

    @property
    def name(self) -> str:
        """Name of the widget class, used in log messages."""
        return type(self._widget).__qualname__

    def matches(self, module: str) -> bool:
        """Return True if changes to `module` should rebuild the widget."""
        return any(module == name or module.startswith(f"{name}.") for name in self.modules)

    def rebuild(self) -> bool:
        """Create a new widget with the factory and put it in place of the old one. Returns True on success.

        Nothing is done if the old widget was deleted (e.g. a dialog that was closed). If the factory raises, the
        old widget is kept.
        """
        old = self._widget
        if not is_alive(old):
            self._reloader.log_message(f"Not rebuilding '{self.name}' - the widget was deleted")
            return False
        try:
            new = self._factory()
        except Exception as e:  # a broken factory must not break the application
            logger.warning("Failed to rebuild %s", self.name, exc_info=True)
            self._reloader.log_message(f"Failed to rebuild '{self.name}' Error={type(e).__name__}: {e}", logging.ERROR)
            return False
        replace_widget(old, new)
        self._widget = new
        self._reloader.log_message(f"Rebuilt '{self.name}'")
        self.evt_rebuilt.emit(new)
        return True

    def unregister(self) -> None:
        """Stop rebuilding the widget. The current widget is kept."""
        self._reloader.unregister_factory(self)

    def _disconnect(self) -> None:
        with suppress(RuntimeError, TypeError):
            self._reloader.evt_batch_reloaded.disconnect(self._on_batch_reloaded)

    def _on_batch_reloaded(self, results: list[ReloadResult]) -> None:
        relevant = [result for result in results if self.matches(result.module)]
        if not relevant:
            return
        failed = [result.module for result in relevant if not result.ok]
        if failed:
            self._reloader.log_message(
                f"Not rebuilding '{self.name}' because {', '.join(failed)} failed to reload", logging.WARNING
            )
            return
        if any(result.changed for result in relevant):
            self.rebuild()
