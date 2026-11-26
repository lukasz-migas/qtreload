"""A panel to edit while running the examples."""

from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class DemoPanel(QWidget):
    """Display a message that can be changed while the application is running."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.message = QLabel("Click the button, then edit examples/panel.py.")
        button = QPushButton("Show message")
        button.clicked.connect(self.show_message)
        layout.addWidget(self.message)
        layout.addWidget(button)

    def show_message(self) -> None:
        """Update the label when the button is clicked."""
        self.message.setText("Hello from the running application!")
