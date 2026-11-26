# qtreload

qtreload reloads edited Python modules inside a running Qt application. It can also reapply stylesheets, rebuild widgets, and help you find the source of a widget on screen.

During Qt development, restarting an application often means reopening a project, navigating to a dialog, and restoring its state before you can check a small change. qtreload watches your files so you can edit a method and try it again in the running application. The project was inspired by the PyDev debugger's auto-reload feature.

Reloading has limits: existing widgets do not rerun their constructors, and some Python changes require a restart. Read [limitations](limitations.md) before relying on a reload.

## Install

qtreload requires Python 3.10 or later and a supported Qt binding. Install one with the package:

```bash
pip install "qtreload[pyqt6]"
# Alternatively:
pip install "qtreload[pyside6]"
```

If your application already provides a Qt binding, `pip install qtreload` is enough. PyQt5 and PySide2 extras are also available; binding availability depends on your Python version and platform. qtreload uses [QtPy](https://github.com/spyder-ide/qtpy) to select the binding.

## Run your application

```bash
qtreload --watch myapp,myplugin my_app.py
```

Press `Ctrl+Shift+F12` (`Cmd+Shift+F12` on macOS) to open the developer tools. Edit and save a method in an imported module, then call it again in the application. Reload messages appear in the tools.

To run a module instead of a script:

```bash
python -m qtreload -m myapp.main
```

Without `--watch` or configured modules, this watches the top-level `myapp` package. See [usage](usage.md) for embedding the tools and working with stylesheets and widgets.

## Build the documentation

From a checkout, use [uv](https://docs.astral.sh/uv/) to install the documentation dependencies and start a local preview:

```bash
uv sync --no-dev --group docs
uv run --no-sync zensical serve
```

To build the site into `site/`, run `uv run --no-sync zensical build --strict --clean`.

The reloading engine is adapted from the [PyDev debugger](https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py) by Fabio Zadrozny.
