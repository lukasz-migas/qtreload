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

It operates by first generating a list of all possible module/submodule files and then watching for any changes using the   `QFileWatcher`. Once a change is detected, the module
is reloaded and the changes are reflected in the application.

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

## When it works like magic

 There are countless examples where this approach really well. Some examples:

 - You are running your application where you have method `on_run` but when you execute this function, you notice that you misspelled some variable. In normal circumstances you would need to restart the application. Now, however, you can correct it in your IDE, save, and try running again.
 - You are running your application and are modifying the layout of a popup window. Now you can do this and each time the dialog is reshown, the new version of the dialog will be shown.
 - You are modifying a Qt style file (`*.qss`) and want to see the changes immediately (subscribe to `evt_stylesheet`)

## Limitations

While this approach can be extremely useful and can save a lot of time, it has a couple of limitations:

- code within the `___init__.py` cannot be reloaded (most of the time)
- some changes to GUI code cannot be hot-reloaded - if e.g., you are modifying the `QMainWindow` and just added a new button, this button will not be shown. In order to show it, you will still need to restart the application. If, however, you were modifying a plugin or a dialog that is shown upon clicking on e.g. menu item, these changes WILL take place.
- modifying python properties (@setter/@getter) is not always reloaded (they will be reflected if you are adding a new property but not if you are changing existing property)
- new files are not reloaded since they were not initially added to the `watched` list - you can refresh file list

## Acknowledgements

The hot-reload code is directly copied from the PyDev debugger developed by [fabioz](https://github.com/fabioz) with minimal changes to remove any dependencies

See https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py

