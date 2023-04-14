# qtreload
 Qt utilities to enable hot-reloading of python/Qt code

[![License](https://img.shields.io/pypi/l/qtreload.svg?color=green)](https://github.com/lukasz-migas/qtreload/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qtreload.svg?color=green)](https://pypi.org/project/qtreload)
[![Python
Version](https://img.shields.io/pypi/pyversions/qtreload.svg?color=green)](https://python.org)
[![Test](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml/badge.svg)](https://github.com/lukasz-migas/qtreload/actions/workflows/test_and_deploy.yml)
[![codecov](https://codecov.io/gh/lukasz-migas/qtreload/branch/main/graph/badge.svg?token=dcsjgl1sOi)](https://codecov.io/gh/lukasz-migas/qtreload)

Have you been using Jupyter Notebook's magic functions such as 

```
%load_ext autoreload
%autoreload 2
```

where you might have been editing code in VSCode or Pycharm and executing actions in Jupyter Notebook?

Or have you previously used [LiClipse](https://www.liclipse.com/) which has [Debugger Auto-Reload](https://www.pydev.org/manual_adv_debugger_auto_reload.html)?

Well, `qtreload` provides similar capabilities by 'hot-reloading' python modules when there are changes to
the source code. It operates by generating a list of all possible modules/submodules for a specific project and
then using `QFileWatcher` to observe any changes to these files.

This library should be used when developing Qt code in Python and you are not interested in continually having to restart your application. (See limitations to find out when its still required).


## Usage

You can instantiate the `QtReloadWidget` manually or using the `install_hot_reload` function.

Note! Make sure to instantiate QApplication before running this code.


Using `QtReloadWidget`:

```
from qtreload.qt_reload import QtReloadWidget

# you can specify list of modules that should be monitored
list_of_widgets = ["napari", "spyder", "..."]

widget = QtReloadWidget(list_of_modules)
```

That's pretty much it. Now every time you make changes to your source code in e.g. `napari` will be reflected in your interpreter.

Using `install_hot_reload` requires two environment variabels being set, namely:

```
QTRELOAD_HOT_RELOAD=1
QTRELOAD_HOT_RELOAD_MODULES="napari, spyder"
```

Then you can just execute the following:
```
from qtreload.install import install_hot_reload

install_hot_reload()
```

## When it works like magic

 There are countless examples where this approach really well. Some examples:

 - You are running your application where you have method `on_run` but when you execute this function, you notice that you misspelled some variable. In normal circumstances you would need to restart the application. Now, however, you can correct it in your IDE, save, and try running again.
 - You are running your application and are modifying the layout of a popup window. Now you can do this and each time the dialog is reshown, the new version of the dialog will be shown.

## Limitations

While this approach can be extremely useful and can save a lot of time, it has a couple of limitations:

- code within the `___init__.py` cannot be reloaded
- some changes to GUI code cannot be reloaded - if e.g. you are modying the `QMainWindow` and just added a new button, this button will now be shown. In order to show it, you will still need to restart the application. If, however, you were modyfing a plugin or a dialog that is shown upon clicking on e.g. menu item, these changes WILL take place.
- modifying python properties (@setter/@getter) is not always reloaded


## Acknowledgements

The hot-reload code is directly copied from the PyDev debugger developed by [fabioz](https://github.com/fabioz) with minimal changes to remove any dependencies

See https://github.com/fabioz/PyDev.Debugger/blob/main/_pydevd_bundle/pydevd_reload.py

