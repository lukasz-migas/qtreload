# Examples

Run these commands from the repository root after installing qtreload and a Qt binding. For example, `uv sync --extra pyside6` installs the project with PySide6.

Each window has an editor with a Save button. Saving writes to the example files in this checkout, so your changes persist after closing the window. Restore the original files with `git restore examples/panel.py examples/style.qss` when you have finished experimenting, if you do not want to keep your changes.

## Command-line launcher

```bash
python -m qtreload --watch examples --show -m exa mples.app
```

Click "Show message", then change the text in `DemoPanel.show_message` in the editor. Click Save and then click "Show message" again to see the new message. The qtreload window shows the reload log. You can also open or hide it with the configured shortcut.

## Embedded controls

```bash
python -m examples.embedded
```

The panel, editor, and reload controls share a window. Edit `DemoPanel.show_message`, click Save, and click the panel's button again. The controls let you change the watch list and pause reloading.

## Rebuild a widget and reload a stylesheet

```bash
python -m examples.live_widget
```

Select the `style.qss` editor tab, change a color, and click Save. To try widget rebuilding, select `panel.py`, change the initial label text or add a button in `DemoPanel.__init__`, and click Save. The existing panel is replaced with a new instance. Reload results are printed in the terminal.

Rebuilding creates a new widget, so its state is reset. Use `live.evt_rebuilt` to reconnect signals that belong to the old instance. See the [usage guide](../docs/usage.md) for more details.
