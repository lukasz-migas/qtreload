"""A small editor for the files used by the demonstrations."""

from pathlib import Path

from qtpy.QtWidgets import QLabel, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget


class FileEditor(QWidget):
    """Edit and save one example file."""

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Editing: {path}"))
        self.text = QPlainTextEdit()
        self.text.setPlainText(path.read_text(encoding="utf-8"))
        layout.addWidget(self.text)
        self.status = QLabel("Changes are saved to this file.")
        layout.addWidget(self.status)
        button = QPushButton("Save")
        button.clicked.connect(self.save)
        layout.addWidget(button)
        self.text.textChanged.connect(lambda: self.status.setText("Unsaved changes"))

    def save(self) -> None:
        """Write the editor contents to the example file."""
        try:
            self.path.write_text(self.text.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Could not save file", str(error))
            return
        self.status.setText("Saved")


class ExampleEditor(QTabWidget):
    """Show an editor tab for each example file."""

    def __init__(self, *filenames: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        for filename in filenames:
            self.addTab(FileEditor(Path(__file__).with_name(filename), self), filename)
