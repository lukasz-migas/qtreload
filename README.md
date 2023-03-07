# qtreload
 Qt utilities to enable hot-reloading of python/Qt code


Have you been using Jupyter Notebook's magic functions such as 

```
%load_ext autoreload
%autoreload 2
```

where you might have been editing code in VSCode or Pycharm and executing actions in Jupyter Notebook?

Well, this tiny library provides similar capabilities by 'hot-reloading' python modules when there are changes to
the source code. It operates by generating a list of all possible modules/submodules for a specific project and
then using `QFileWatcher` to observe any changes to these files.


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

Using `install_hot_reload` requires two environment variabels being set, namely

`QTRELOAD_HOT_RELOAD=1`
`QTRELOAD_HOT_RELOAD_MODULES="napari, spyder"`

```
from qtreload.install import install_hot_reload

install_hot_reload()
```


