"""A Qt application to run with the qtreload command-line launcher."""

import sys

from qtpy.QtWidgets import QApplication, QHBoxLayout, QWidget

from examples.editor import ExampleEditor
from examples.panel import DemoPanel


def main() -> int:
    """Show the panel and run the Qt event loop."""
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("qtreload launcher example")
    layout = QHBoxLayout(window)
    layout.addWidget(DemoPanel())
    layout.addWidget(ExampleEditor("panel.py"))
    window.resize(1000, 600)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
