# Examples

Run these commands from the repository root after installing qtreload and a Qt binding. For example, `uv sync --extra pyside6` installs the project with PySide6.

## Command-line launcher

```bash
python -m qtreload --watch examples --show -m examples.app
```

Click "Show message", then change the text in `DemoPanel.show_message` in `examples/panel.py`. Save the file and click again to see the new message. The qtreload window shows the reload log. You can also open or hide it with the configured shortcut.

## Embedded controls

```bash
python -m examples.embedded
```

The panel and reload controls share a window. Edit `DemoPanel.show_message` and click the button again after saving. The controls let you change the watch list and pause reloading.

## Rebuild a widget and reload a stylesheet

```bash
python -m examples.live_widget
```

Edit `examples/style.qss` and save it to update the application's colors. To try widget rebuilding, change the initial label text or add a button in `DemoPanel.__init__`, then save `examples/panel.py`. The existing panel is replaced with a new instance. Reload results are printed in the terminal.

Rebuilding creates a new widget, so its state is reset. Use `live.evt_rebuilt` to reconnect signals that belong to the old instance. See the [usage guide](../docs/usage.md) for more details.
