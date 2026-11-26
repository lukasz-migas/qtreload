# Reload limitations

qtreload watches Python files and package directories using Qt's file system watcher. It picks up files added or deleted after startup and handles editors that replace files when saving. A new file must be imported by the application before it can be reloaded.

- Existing widgets do not rerun `__init__`. Reopen the widget, [register a factory](usage.md#rebuild-widgets), or restart the application to see construction changes.
- Module and class constants retain their existing values. Functions, methods, properties, decorated functions, and dataclass fields can be updated.
- Adding, removing, or changing enum members and changing closure variables of module-level functions require a restart. qtreload logs a warning for these changes.
- `__init__.py`, `_version.py`, and `test_*.py` files are ignored by default. Change `ignore_py_pattern` if you need to watch them.
- Changes made while reloading is paused are skipped. Resume and use "Reload python files" to apply them.

If the running application does not behave as expected after a reload, check the developer tools for errors and restart it before continuing.
