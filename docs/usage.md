# Usage

## Launch an application

Pass qtreload options before the script or `-m` and pass application arguments after it:

```bash
qtreload --watch myapp,myplugin my_app.py --app-argument
qtreload --show --settings-key myapp -m myapp.main
qtreload --shortcut "Ctrl+Shift+F10" --watch myapp my_app.py
```

`--show` opens the tools at startup. Otherwise, use `Ctrl+Shift+F12` (`Cmd+Shift+F12` on macOS) to toggle them. `--watch` accepts a comma-separated list and can be repeated. It overrides configured modules; without it, qtreload uses [configuration](configuration.md) or, for `-m`, the module's top-level package.

The launcher installs the tools when `QApplication.exec()` or `exec_()` starts. If an application does not start its own event loop, call `install_dev_tools()` after creating the `QApplication`.

## Install the developer tools in code

```python
import sys

from qtpy.QtWidgets import QApplication, QLabel
from qtreload import install_dev_tools

app = QApplication(sys.argv)
window = QLabel("My application")
window.show()
tools = install_dev_tools(show=True, settings_key="myapp")
sys.exit(app.exec())
```

Set the modules to watch in `pyproject.toml` or in the tools window. `install_dev_tools()` returns the existing tools window if called again. The window does not keep the application running when the other windows close.

## Embed a reload widget

For an opt-in development panel, set `QTRELOAD_HOT_RELOAD=1` and configure modules before starting your application:

```bash
export QTRELOAD_HOT_RELOAD=1
export QTRELOAD_HOT_RELOAD_MODULES=myapp,myplugin
python my_app.py
```

Add the widget after creating the application. The function returns `None` when the opt-in variable is not `1`.

```python
import sys

from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget
from qtreload import install_hot_reload

app = QApplication(sys.argv)
window = QWidget()
layout = QVBoxLayout(window)
reload_widget = install_hot_reload(parent=window, settings_key="myapp")
if reload_widget is not None:
    layout.addWidget(reload_widget)
window.show()
sys.exit(app.exec())
```

You can also create `QtReloadWidget(["myapp"], parent=window)` directly. Keep a reference to the widget or give it a Qt parent.

## Use the reloader without a panel

`HotReloader` does the watching and reloading without a user interface. A `QtReloadWidget` exposes its instance as `widget.reloader`.

```python
from qtpy.QtWidgets import QApplication
from qtreload import HotReloader

app = QApplication.instance() or QApplication([])
reloader = HotReloader(["myapp"], parent=app)
reloader.evt_reloaded.connect(lambda result: print(result.summary()))
reloader.evt_reload_failed.connect(lambda result: print(result.traceback))
reloader.add_module("myplugin")
reloader.set_patterns(stylesheet_pattern=("**/*.qss", "**/*.css"))
# Start or continue the application's event loop here.
```

Keep a reference to the reloader or give it a Qt parent. `evt_pyfile` emits the reloaded module name. `evt_reloaded` and `evt_reload_failed` provide a result with the outcome and any traceback.

## Reload stylesheets

Register an existing stylesheet to apply it immediately and again when it changes. It can live outside the watched packages.

```python
reloader.register_stylesheet("styles/app.qss")  # Applies to QApplication.
reloader.register_stylesheet("styles/panel.qss", target=panel, variables=lambda: {"accent": "#4488cc"})
```

The second file can use a `{{ accent }}` placeholder. A callable supplies fresh variables each time the stylesheet is applied; call `reloader.apply_stylesheets()` after changing a theme. Stylesheets registered for the same target are joined in registration order. Keep the target alive for as long as it is needed.

`evt_stylesheet_changed` emits each changed path, while `evt_stylesheet` fires once per batch. The example assumes `reloader` and `panel` already exist.

## Rebuild widgets

An existing widget does not rerun `__init__` when its module reloads. Register a factory to create a replacement and put it into the existing layout:

```python
from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget
from qtreload import HotReloader
from myapp.panels import SettingsPanel

app = QApplication.instance() or QApplication([])
window = QWidget()
layout = QVBoxLayout(window)
reloader = HotReloader(["myapp"], parent=app)
live = reloader.register_factory(lambda: SettingsPanel(), modules=["myapp.panels"])
layout.addWidget(live.widget)
window.show()
app.exec()
```

The widget class and factory modules trigger rebuilds, along with any modules supplied in `modules`. The replacement is made once per successful reload batch. Layouts, splitters, tabs, docks, scroll areas, central widgets, and top-level windows are supported. A deleted widget is not rebuilt.

Connect `live.evt_rebuilt` to reconnect signals on the new widget. While the factory runs, `live.widget` still points to the old instance, so a factory can copy state before returning the replacement.

## Pause and resume

Use the panel's "Pause reloading" control or `reloader.set_paused(True)` while switching branches or generating files. Changes made while paused are not reloaded. Resume and use "Reload python files" if you want to apply them.
