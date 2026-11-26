"""Embed the reload controls alongside a panel."""

import sys

from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget

from examples.panel import DemoPanel
from qtreload import QtReloadWidget


def main() -> int:
    """Show the example panel and reload controls."""
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("qtreload embedded example")
    layout = QHBoxLayout(window)
    layout.addWidget(DemoPanel())
    layout.addWidget(QtReloadWidget(["examples"], parent=window))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
