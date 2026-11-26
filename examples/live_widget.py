"""Rebuild a panel and reapply a stylesheet when their files change."""

import sys
from pathlib import Path

from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget

from examples.panel import DemoPanel
from qtreload import HotReloader


def main() -> int:
    """Show a panel managed by a reloader."""
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("qtreload live widget example")
    layout = QVBoxLayout(window)

    reloader = HotReloader(["examples"], parent=app)
    reloader.evt_reloaded.connect(lambda result: print(result.summary()))
    reloader.evt_reload_failed.connect(lambda result: print(result.traceback))
    reloader.register_stylesheet(Path(__file__).with_name("style.qss"))
    live = reloader.register_factory(DemoPanel)
    layout.addWidget(live.widget)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
