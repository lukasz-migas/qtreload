"""Rebuild a panel and reapply a stylesheet when their files change."""

import sys
from pathlib import Path

from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget
from qtreload import HotReloader

from examples.editor import ExampleEditor
from examples.panel import DemoPanel


def main() -> int:
    """Show a panel managed by a reloader."""
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("qtreload live widget example")
    layout = QHBoxLayout(window)

    reloader = HotReloader(["examples"], parent=app)
    reloader.evt_reloaded.connect(lambda result: print(result.summary()))
    reloader.evt_reload_failed.connect(lambda result: print(result.traceback))
    reloader.register_stylesheet(Path(__file__).with_name("style.qss"))
    live = reloader.register_factory(DemoPanel)
    layout.addWidget(live.widget)
    layout.addWidget(ExampleEditor("panel.py", "style.qss"))

    window.resize(1000, 600)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
