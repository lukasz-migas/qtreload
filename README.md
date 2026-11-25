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

Using `install_hot_reload` requires two environment variables being set, namely:

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

## When it works like magic

 There are countless examples where this approach really well. Some examples:

 - You are running your application where you have method `on_run` but when you execute this function, you notice that you misspelled some variable. In normal circumstances you would need to restart the application. Now, however, you can correct it in your IDE, save, and try running again.
 - You are running your application and are modifying the layout of a popup window. Now you can do this and each time the dialog is reshown, the new version of the dialog will be shown.
 - You are modifying a Qt style file (`*.qss`) and want to see the changes immediately (use `register_stylesheet` or subscribe to `evt_stylesheet`)

## Limitations

While this approach can be extremely useful and can save a lot of time, it has a couple of limitations:

- `__init__.py` files are not watched by default - remove `**/__init__.py` from the ignore pattern to reload them too
- some changes to GUI code cannot be hot-reloaded - if e.g., you are modifying the `QMainWindow` and just added a new button, this button will not be shown. In order to show it, you will still need to restart the application. If, however, you were modifying a plugin or a dialog that is shown upon clicking on e.g. menu item, these changes WILL take place.
- module and class level constants are not changed on reload (so application state is kept) - functions, methods, properties, decorated functions and dataclass fields are updated
- adding, removing or changing enum members and changing closure variables of module-level functions require a restart (a warning is shown in the log)
- new files are watched as soon as they are created, but they are only reloaded once your application has imported them

## Acknowledgements

The hot-reload code is directly copied from the PyDev debugger developed by [fabioz](https://github.com/fabioz) with minimal changes to remove any dependencies

See https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py

