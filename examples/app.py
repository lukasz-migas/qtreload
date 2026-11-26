"""A Qt application to run with the qtreload command-line launcher."""

import sys

from qtpy.QtWidgets import QApplication

from examples.panel import DemoPanel


def main() -> int:
    """Show the panel and run the Qt event loop."""
    app = QApplication(sys.argv)
    panel = DemoPanel()
    panel.setWindowTitle("qtreload launcher example")
    panel.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
