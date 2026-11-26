"""Embed the reload controls alongside a panel."""

import sys

from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget
from qtreload import QtReloadWidget

from examples.editor import ExampleEditor
from examples.panel import DemoPanel


def main() -> int:
    """Show the example panel and reload controls."""
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("qtreload embedded example")
    layout = QHBoxLayout(window)
    layout.addWidget(DemoPanel())
    layout.addWidget(ExampleEditor("panel.py"))
    layout.addWidget(QtReloadWidget(["examples"], parent=window))
    window.resize(1400, 700)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
