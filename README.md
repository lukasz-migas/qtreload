# qtreload

[![License](https://img.shields.io/pypi/l/qtreload.svg?color=green)](https://github.com/lukasz-migas/qtreload/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qtreload.svg?color=green)](https://pypi.org/project/qtreload)
[![Python version](https://img.shields.io/pypi/pyversions/qtreload.svg?color=green)](https://python.org)
[![Tests](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml)

qtreload watches Python modules and stylesheets while your Qt application runs. Save a method, then try it again in the running application. You can also rebuild widgets when their construction code changes, inspect widgets, and reload QSS files.

The project grew out of missing the PyDev debugger's auto-reload feature after moving to PyCharm. It brings a similar development workflow to Python Qt applications, where restarting an application and navigating back to a widget can take time. Some changes still require recreating a widget or restarting the application; see [limitations](https://lukasz-migas.github.io/qtreload/limitations/).

## Installation

Install qtreload and a Qt binding. If your application already has a supported binding, install `qtreload` on its own.

```bash
pip install "qtreload[pyqt6]"
# Or use another supported binding, for example:
pip install "qtreload[pyside6]"
```

qtreload requires Python 3.10 or later and uses [QtPy](https://github.com/spyder-ide/qtpy) to work with PyQt or PySide.

## Quick start

Run an existing application through qtreload, with the packages you want to watch:

```bash
qtreload --watch myapp,myplugin my_app.py --app-argument
```

Open the developer tools with `Ctrl+Shift+F12` (`Cmd+Shift+F12` on macOS). Edit a method in an imported module, save the file, and call the method again in the application. The tools show reload messages and let you change the watch list.

You can also run a module. If no modules are configured, qtreload watches its top-level package:

```bash
python -m qtreload -m myapp.main
qtreload --show --settings-key myapp -m myapp.main
```

The launcher installs the tools when the application starts its Qt event loop. Use `--shortcut` to change the shortcut. See the [usage guide](https://lukasz-migas.github.io/qtreload/usage/) for applications that do not start an event loop.

## Add developer tools to an application

Create the `QApplication` first, then install the tools. Configure the modules to watch in `pyproject.toml` or with `QTRELOAD_HOT_RELOAD_MODULES`.

```python
import sys

from qtpy.QtWidgets import QApplication, QLabel
from qtreload import install_dev_tools

app = QApplication(sys.argv)
window = QLabel("Edit myapp while this window is open")
window.show()
tools = install_dev_tools(show=True)  # Keep a reference to the tools.
sys.exit(app.exec())
```

```toml
[tool.qtreload]
modules = ["myapp"]
```

For an opt-in widget embedded in your own interface, use `install_hot_reload()`. It returns `None` unless `QTRELOAD_HOT_RELOAD=1` is set. See [configuration](https://lukasz-migas.github.io/qtreload/configuration/) for the available settings.

## Reload a stylesheet

A `HotReloader` can watch a QSS file even when it is outside a watched package. Create the file before registering it.

```python
from qtpy.QtWidgets import QApplication, QLabel
from qtreload import HotReloader

app = QApplication.instance() or QApplication([])
window = QLabel("Save styles/app.qss to update me")
window.show()
reloader = HotReloader(["myapp"], parent=app)
reloader.register_stylesheet("styles/app.qss")
app.exec()
```

## Rebuild a widget

Changes to a widget's `__init__` need a new instance. Register a factory to replace the existing widget when its module reloads:

```python
from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget
from qtreload import HotReloader
from myapp.panels import SettingsPanel

app = QApplication.instance() or QApplication([])
window = QWidget()
layout = QVBoxLayout(window)
reloader = HotReloader(["myapp"], parent=app)
live = reloader.register_factory(lambda: SettingsPanel())
layout.addWidget(live.widget)
window.show()
app.exec()
```

Connect to `live.evt_rebuilt` to reconnect signals on the replacement. See [usage](https://lukasz-migas.github.io/qtreload/usage/) for more examples and caveats.

## Documentation

Read the [documentation](https://lukasz-migas.github.io/qtreload/) for configuration, the widget inspector, stylesheets, and reload limitations.

To build the documentation locally from a checkout:

```bash
uv sync --no-dev --group docs
uv run --no-sync zensical serve
# Or build the site in site/:
uv run --no-sync zensical build --strict --clean
```

## Acknowledgements

The module reloading engine is adapted from the [PyDev debugger](https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py) by Fabio Zadrozny.
