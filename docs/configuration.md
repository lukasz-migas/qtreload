# Configuration

qtreload reads the nearest `pyproject.toml` containing a `[tool.qtreload]` table, searching from the current directory upwards:

```toml
[tool.qtreload]
modules = ["myapp", "myplugin"]
py_pattern = ["**/*.py"]
ignore_py_pattern = ["**/__init__.py", "**/_version.py", "**/test_*.py"]
stylesheet_pattern = ["**/*.qss"]
delay_ms = 500
editor = "code -g {path}:{line}"
```

These patterns and delay are the defaults; the module list is empty by default. The delay groups file changes before reloading. The editor command is optional and uses `{path}` and `{line}` placeholders.

Environment variables override the corresponding configuration values. Lists are comma separated; an empty list variable clears the list.

| Setting | Environment variable |
| --- | --- |
| `modules` | `QTRELOAD_HOT_RELOAD_MODULES` |
| `py_pattern` | `QTRELOAD_PY_PATTERN` |
| `ignore_py_pattern` | `QTRELOAD_IGNORE_PY_PATTERN` |
| `stylesheet_pattern` | `QTRELOAD_STYLESHEET_PATTERN` |
| `delay_ms` | `QTRELOAD_DELAY_MS` |
| `editor` | `QTRELOAD_EDITOR` |

For example:

```bash
export QTRELOAD_HOT_RELOAD_MODULES=myapp,myplugin
export QTRELOAD_DELAY_MS=300
```

`qtreload.load_config()` reads these settings, as do the launcher, `install_dev_tools()`, `install_hot_reload()`, and `HotReloader.from_config()`. The launcher option `--watch` overrides the configured module list. `install_hot_reload()` additionally requires `QTRELOAD_HOT_RELOAD=1`.

## Remember changes in the tools

Pass a settings key to remember changes to modules, patterns, and the paused state across sessions:

```python
tools = install_dev_tools(settings_key="myapp")
```

Remembered values take precedence over configured values until you press "Reset" in the tools. You can also pass `settings_key` to `QtReloadWidget`, `HotReloader`, or `install_hot_reload()`.
