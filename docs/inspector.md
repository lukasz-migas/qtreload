# Widget inspector

The developer tools include an Inspector tab for finding the class and source of a widget in a running application.

1. Open the tools and select the Inspector tab.
2. Press "Pick widget", move the cursor over the application, and click the widget outlined in red. The click selects the widget without activating it; press Escape to cancel.
3. Read its class, module, source file and line, object name, geometry, parents, and stylesheet. Use "Select parent" to move up the hierarchy or "Open source" to open the class in your editor.

You can also open files from the Files tab's context menu. Configure an editor command with `editor` in `[tool.qtreload]`, `QTRELOAD_EDITOR`, or `QtReloadWidget(editor=...)`. For example:

```toml
[tool.qtreload]
editor = "pycharm --line {line} {path}"
```

For VS Code, use `code -g {path}:{line}`. Without a configured editor, files open using the application associated with their type. See [configuration](configuration.md) for precedence.

The same tools are available in Python as `WidgetInspector`, `describe_widget`, and `open_in_editor`.
