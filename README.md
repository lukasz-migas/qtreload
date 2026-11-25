# qtreload
 Qt utilities to enable hot-reloading of python/Qt code

[![License](https://img.shields.io/pypi/l/qtreload.svg?color=green)](https://github.com/lukasz-migas/qtreload/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qtreload.svg?color=green)](https://pypi.org/project/qtreload)
[![Python
Version](https://img.shields.io/pypi/pyversions/qtreload.svg?color=green)](https://python.org)
[![Test](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml)
[![codecov](https://codecov.io/gh/lukasz-migas/qtreload/branch/main/graph/badge.svg?token=dcsjgl1sOi)](https://codecov.io/gh/lukasz-migas/qtreload)

Have you used Jupyter Notebook's magic functions such as 

```python
%load_ext autoreload
%autoreload 2
```

where you might have been editing code in VSCode or Pycharm and executing actions in Jupyter Notebook?

or perhaps you previously used [LiClipse](https://www.liclipse.com/) which has [Debugger Auto-Reload](https://www.pydev.org/manual_adv_debugger_auto_reload.html)?

Well, I used to love LiClipse and the hot-reload functionality, but I moved my day-to-day development to PyCharm due to it's superior plugin environment. Despite this, I always missed
the hot-reload functionality, especially when developing Qt applications in Python.

Anyway, `qtreload` is a small library that provides a similar hot-reload functionality when developing Qt code in Python.

It operates by first generating a list of all possible module/submodule files and then watching for any changes using the `QFileSystemWatcher`. Once a change is detected, the module
is reloaded and the changes are reflected in the application. Package directories are watched too, so files that you add or delete later are picked up automatically,
and editors that save by replacing the file (e.g. PyCharm's "safe write" or vim) keep working after the first save.

This library should be used when developing Qt code in Python and you are not interested in continually having to restart your application. Please see the limitations section to find out when it's still required.


## Installation

You can install `qtreload` using `pip`:

```bash
pip install qtreload
```

## Usage

### Without changing your application

Run your application through `qtreload` to get hot reloading without touching its code:

```bash
python -m qtreload --watch myapp,myplugin my_app.py --app-argument
python -m qtreload -m myapp.main            # watches the 'myapp' package by default
qtreload --show --settings-key myapp my_app.py
```

The developer tools window opens with `Ctrl+Shift+F12` (`Cmd+Shift+F12` on macOS) from any window of the application
(change it with `--shortcut`). Without `--watch`, the modules come from `[tool.qtreload]` in `pyproject.toml` or the
`QTRELOAD_*` environment variables (see Configuration), or the package of the module run with `-m`. Hot reloading
starts when the application starts its event loop (`app.exec()`). If it never does (e.g. in an interactive session),
call `install_dev_tools()` yourself once the `QApplication` exists - it does the same as the command line.

### In your application code

You can instantiate the `QtReloadWidget` manually or using the `install_hot_reload` function.

Note! Make sure to instantiate QApplication before running this code.


Using `QtReloadWidget`:

```
from qtreload import QtReloadWidget

# you can specify list of modules that should be monitored
list_of_modules = ["napari", "napari_plugin", "..."]

widget = QtReloadWidget(list_of_modules)

# add the widget to your application (or keep reference to it so it's not garbage collected)
app.layout().addWidget(widget)
```

That's pretty much it. Now every time you make changes to your source code in e.g. `napari` will be reflected in your interpreter.

`install_hot_reload` does nothing unless the environment variable `QTRELOAD_HOT_RELOAD=1` is set, so it can stay in
your application code. The modules and patterns come from the configuration (see below):

```
QTRELOAD_HOT_RELOAD=1
QTRELOAD_HOT_RELOAD_MODULES="napari,napari_plugin"
```

Then you can execute the following:
```
from qtreload.install import install_hot_reload

widget = install_hot_reload()

# add the widget to your application (or keep reference to it so it's not garbage collected)
app.layout().addWidget(widget)
```

### Configuration

Instead of passing modules and patterns in code, you can configure them in `pyproject.toml`:

```toml
[tool.qtreload]
modules = ["napari", "napari_plugin"]
py_pattern = ["**/*.py"]
ignore_py_pattern = ["**/__init__.py", "**/test_*.py"]
stylesheet_pattern = ["**/*.qss"]
delay_ms = 500
```

or with environment variables, which win over `pyproject.toml` (lists are comma separated, an empty value means an
empty list): `QTRELOAD_HOT_RELOAD_MODULES`, `QTRELOAD_PY_PATTERN`, `QTRELOAD_IGNORE_PY_PATTERN`,
`QTRELOAD_STYLESHEET_PATTERN` and `QTRELOAD_DELAY_MS`. The nearest `pyproject.toml` with a `[tool.qtreload]` table is used,
searching up from the current directory. `install_hot_reload` uses this configuration, and so do `HotReloader.from_config()`
and `qtreload.load_config()`.

To remember changes made in the widget (modules, patterns and the paused state) between sessions, pass a settings key,
e.g. `install_hot_reload(settings_key="myapp")` or `QtReloadWidget(modules, settings_key="myapp")`. Remembered values are
used instead of the configured ones until you press "Reset".

Tick "Pause reloading" (or call `reloader.set_paused(True)`) while you switch git branches or run code generators. Files
changed while paused are not reloaded, even if their change events arrive late - press "Reload python files" afterwards if
you want to apply them.

### Without a widget

All watching and reloading is done by `HotReloader`, a `QObject` with no user interface. `QtReloadWidget` is a view on top
of it (available as `widget.reloader`). Use `HotReloader` directly if you don't want to show anything:

```python
from qtreload import HotReloader

reloader = HotReloader(["napari", "napari_plugin"], parent=app)
reloader.evt_pyfile.connect(lambda module: print(f"reloaded {module}"))
reloader.evt_stylesheet.connect(apply_my_stylesheet)
# detailed outcome: ReloadResult with .updated, .added, .warnings, .error and .traceback
reloader.evt_reloaded.connect(lambda result: print(result.summary()))
reloader.evt_reload_failed.connect(lambda result: print(result.traceback))

# change what is watched at any time
reloader.add_module("another_module")
reloader.remove_modules(["napari_plugin"])
reloader.set_patterns(stylesheet_pattern=("**/*.qss", "**/*.css"))
```

Keep a reference to it (or give it a parent) so it is not garbage collected.

### Stylesheets

Register a stylesheet to have it applied now and re-applied every time you save it. The file does not have to be
part of a watched module, and several stylesheets registered for the same target are joined in registration order.
QSS has no variables, so you can use `{{ name }}` placeholders and pass their values (or a function returning them,
called every time the stylesheet is applied):

```python
reloader.register_stylesheet("styles/app.qss")  # applied to the QApplication
reloader.register_stylesheet("styles/panel.qss", target=panel, variables=lambda: CURRENT_THEME)

# after changing the theme
reloader.apply_stylesheets()
```

`evt_stylesheet_changed(path)` is emitted for every changed stylesheet, and `evt_stylesheet()` once per batch of changes.

### Rebuilding widgets

Code in `__init__` only runs when a widget is created, so e.g. a new button does not appear in a widget that already
exists. Register a factory to have the widget rebuilt automatically whenever its module changes. The new widget is put
exactly where the old one was (layouts, splitters, tabs, docks, scroll areas, central widget or top-level window):

```python
live = reloader.register_factory(lambda: SettingsPanel(config))
layout.addWidget(live.widget)

# the module of the widget's class and of the factory always trigger a rebuild, add more with `modules`
live = reloader.register_factory(lambda: MainPanel(config), modules=["myapp.panels"])
live.evt_rebuilt.connect(lambda widget: widget.evt_changed.connect(on_changed))
```

The widget is rebuilt once per batch of changes, not when its modules failed to reload, and not if it was deleted in the
meantime (e.g. a dialog that was closed). While the factory runs, `live.widget` is still the old instance, so you can
copy its state to the new one.

### Inspecting widgets

The "Inspector" tab of the widget answers "which class draws this, and where is its code?". Press "Pick widget", hover
over your application (the widget under the cursor gets a red frame) and click a widget - the click selects it without
triggering it, Escape cancels. The tab shows the class, module, source file and line, object name, geometry, parents
and stylesheet. "Select parent" walks up the hierarchy and "Open source" opens the class in your editor.

Files can also be opened from the "Files" tab (right click). Set the editor command with `{path}` and `{line}`
placeholders in `[tool.qtreload] editor`, the `QTRELOAD_EDITOR` environment variable or `QtReloadWidget(editor=...)`,
e.g. `pycharm --line {line} {path}` or `code -g {path}:{line}`. Without one, files open in the application associated
with their type. The same tools are available as `WidgetInspector`, `describe_widget` and `open_in_editor`.

## When it works like magic

 There are countless examples where this approach really well. Some examples:

 - You are running your application where you have method `on_run` but when you execute this function, you notice that you misspelled some variable. In normal circumstances you would need to restart the application. Now, however, you can correct it in your IDE, save, and try running again.
 - You are running your application and are modifying the layout of a popup window. Now you can do this and each time the dialog is reshown, the new version of the dialog will be shown.
 - You are modifying a Qt style file (`*.qss`) and want to see the changes immediately (use `register_stylesheet` or subscribe to `evt_stylesheet`)

## Limitations

While this approach can be extremely useful and can save a lot of time, it has a couple of limitations:

- `__init__.py` files are not watched by default - remove `**/__init__.py` from the ignore pattern to reload them too
- changes to the layout of a widget that already exists (e.g. a new button in `__init__`) are only visible once the widget is created again - register its factory (see above) to have it rebuilt automatically, or restart the application. Dialogs and plugins that are created when opened pick up the changes the next time they are shown.
- module and class level constants are not changed on reload (so application state is kept) - functions, methods, properties, decorated functions and dataclass fields are updated
- adding, removing or changing enum members and changing closure variables of module-level functions require a restart (a warning is shown in the log)
- new files are watched as soon as they are created, but they are only reloaded once your application has imported them

## Acknowledgements

The hot-reload code is directly copied from the PyDev debugger developed by [fabioz](https://github.com/fabioz) with minimal changes to remove any dependencies

See https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py

