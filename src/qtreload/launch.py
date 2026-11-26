"""Run a Qt application with hot reloading, and toggle the developer tools with a shortcut."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import runpy
import sys
import typing as ty

from qtpy.QtCore import QEvent, QObject, Qt
from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import QApplication, QWidget

from qtreload.config import ReloadConfig, load_config

if ty.TYPE_CHECKING:
    from qtreload.qt_reload import QtReloadWidget

__all__ = ["DEFAULT_SHORTCUT", "DevToolsShortcut", "get_dev_tools", "install_dev_tools", "main"]

logger = logging.getLogger(__name__)

# shortcut toggling the developer tools window
DEFAULT_SHORTCUT = "Ctrl+Shift+F12"
# options of the command line that take a value
_VALUE_OPTIONS = ("-w", "--watch", "--settings-key", "--shortcut")

_dev_tools: QtReloadWidget | None = None


class DevToolsShortcut(QObject):
    """Application-wide keyboard shortcut that shows or hides a widget, whichever window has focus.

    Parameters
    ----------
    widget : QWidget
        Window to toggle. It is also the Qt parent of the shortcut.
    sequence : str
        Key sequence, e.g. "Ctrl+Shift+F12".
    """

    def __init__(self, widget: QWidget, sequence: str = DEFAULT_SHORTCUT) -> None:
        super().__init__(widget)
        self.widget = widget
        self.sequence = QKeySequence(sequence)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def toggle(self) -> None:
        """Show (and focus) the widget, or hide it if it is visible."""
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.widget.show()
            self.widget.raise_()
            self.widget.activateWindow()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Toggle the widget when the key sequence is pressed."""
        if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat() and self._matches(event):
            self.toggle()
            return True
        return False

    def _matches(self, event: ty.Any) -> bool:
        if hasattr(event, "keyCombination"):
            pressed = QKeySequence(event.keyCombination())
        else:  # pragma: no cover - Qt5
            pressed = QKeySequence(int(event.modifiers()) | event.key())
        return pressed == self.sequence


def get_dev_tools() -> QtReloadWidget | None:
    """Return the developer tools window created by `install_dev_tools`, if any."""
    return _dev_tools


def install_dev_tools(
    config: ReloadConfig | None = None,
    settings_key: str | None = None,
    shortcut: str = DEFAULT_SHORTCUT,
    show: bool = False,
) -> QtReloadWidget:
    """Start hot reloading and open the developer tools window with a keyboard shortcut.

    The window is a `QtReloadWidget` configured with `config` (loaded with `load_config` if not given). It is hidden
    until `shortcut` is pressed in any window of the application (or `show` is True) and does not keep the
    application running when the other windows are closed. Calling it again returns the existing window.

    Raises
    ------
    RuntimeError
        If no QApplication exists yet.
    """
    global _dev_tools
    from qtreload.qt_reload import QtReloadWidget

    if _dev_tools is not None:
        return _dev_tools
    if QApplication.instance() is None:
        raise RuntimeError("Create a QApplication before installing the developer tools.")

    config = config or load_config()
    widget = QtReloadWidget(config.modules, settings_key=settings_key, editor=config.editor, **config.reloader_kwargs())
    widget.setWindowTitle("qtreload - developer tools")
    widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
    widget.resize(900, 500)
    widget.shortcut = DevToolsShortcut(widget, shortcut)
    widget.log_message(f"Press {widget.shortcut.sequence.toString()} to show or hide the developer tools")
    if not config.modules:
        widget.log_message(
            "No modules are watched - add them here, with --watch or in [tool.qtreload]", logging.WARNING
        )
    if show:
        widget.show()
    _dev_tools = widget
    return widget


class _ExecHook:
    """Run a function once, when the application starts its event loop (QApplication.exec / exec_)."""

    NAMES = ("exec", "exec_")

    def __init__(self, func: ty.Callable[[], ty.Any]) -> None:
        self._func = func
        self._saved: dict[str, tuple[bool, ty.Any]] = {}

    def patch(self) -> None:
        self._saved = {name: (name in QApplication.__dict__, QApplication.__dict__.get(name)) for name in self.NAMES}
        for name in self.NAMES:
            setattr(QApplication, name, self._make_wrapper(name))

    def restore(self) -> None:
        for name, (had, original) in self._saved.items():
            if had:
                setattr(QApplication, name, original)
            elif name in QApplication.__dict__:
                delattr(QApplication, name)
        self._saved = {}

    def _make_wrapper(self, name: str) -> ty.Callable[..., ty.Any]:
        def wrapper(*args: ty.Any) -> ty.Any:
            # works for app.exec() (the application is passed) and QApplication.exec()
            self.restore()
            try:
                self._func()
            except Exception:  # the application must start even if the developer tools cannot be installed
                logger.exception("Could not install the qtreload developer tools")
            target = args[0] if args else QApplication
            return getattr(target, name)()

        return wrapper


def _split_argv(argv: list[str]) -> tuple[list[str], str | None, str | None, list[str]]:
    """Split the command line into (qtreload options, script, module, arguments of the application)."""
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "-m":
            if index + 1 >= len(argv):
                raise SystemExit("qtreload: -m requires a module name")
            return argv[:index], None, argv[index + 1], argv[index + 2 :]
        if arg in _VALUE_OPTIONS:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        return argv[:index], arg, None, argv[index + 1 :]
    return argv, None, None, []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qtreload",
        usage="qtreload [options] (script.py | -m module) [arguments of the application]",
        description=(
            "Run a Qt application with hot reloading. The developer tools are toggled with a keyboard shortcut. "
            "Modules and patterns are read from [tool.qtreload] in pyproject.toml and QTRELOAD_* environment "
            "variables, --watch replaces the modules."
        ),
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="append",
        default=[],
        metavar="MODULES",
        help="comma separated modules to watch (can be repeated) - defaults to the configured modules, or the "
        "package of the module run with -m",
    )
    parser.add_argument("--settings-key", help="remember changes made in the developer tools under this key")
    parser.add_argument(
        "--shortcut", default=DEFAULT_SHORTCUT, help=f"shortcut to toggle the tools ({DEFAULT_SHORTCUT})"
    )
    parser.add_argument("--show", action="store_true", help="show the developer tools when the application starts")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface (`python -m qtreload` or `qtreload`)."""
    options, script, module, app_args = _split_argv(list(sys.argv[1:] if argv is None else argv))
    parser = _parser()
    args = parser.parse_args(options)
    if script is None and module is None:
        parser.error("specify the script or the module (-m) to run")

    config = load_config()
    watch = tuple(dict.fromkeys(name.strip() for value in args.watch for name in value.split(",") if name.strip()))
    if watch:
        config = dataclasses.replace(config, modules=watch)
    elif not config.modules and module is not None:
        config = dataclasses.replace(config, modules=(module.split(".")[0],))

    hook = _ExecHook(
        lambda: install_dev_tools(config, settings_key=args.settings_key, shortcut=args.shortcut, show=args.show)
    )
    old_argv, old_path = sys.argv[:], sys.path[:]
    hook.patch()
    try:
        if module is not None:
            sys.argv = [module, *app_args]
            sys.path.insert(0, os.getcwd())
            runpy.run_module(module, run_name="__main__", alter_sys=True)
        else:
            sys.argv = [script, *app_args]
            sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
            runpy.run_path(script, run_name="__main__")
    finally:
        hook.restore()
        sys.argv, sys.path[:] = old_argv, old_path
    return 0


def cli() -> None:
    """Entry point of the `qtreload` console script."""
    sys.exit(main())
