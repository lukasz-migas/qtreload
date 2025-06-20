"""SampleWidget that contains many types of QWidgets.

This file and SampleWidget is useful for testing out themes from the command
line or for generating screenshots of a sample widget to demonstrate a theme.

Examples
--------
To use from the command line:

$ python -m napari._qt.theme_sample

To generate a screenshot within python:
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollBar,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from qtreload import QtReloadWidget

blurb = """
<h3>Heading</h3>
<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit,
sed do eiusmod tempor incididunt ut labore et dolore magna
aliqua. Ut enim ad minim veniam, quis nostrud exercitation
ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit
esse cillum dolore eu fugiat nulla pariatur. Excepteur
sint occaecat cupidatat non proident, sunt in culpa qui
officia deserunt mollit anim id est laborum.</p>
"""

STYLESHEET = """
    QLabel#success {
        color: green;
    }
    QLabel#warning {
        color: orange;
    }
    QLabel#active {
        color: blue;
    }
    QLabel#standout {
        color: red;
    }
"""


class TabDemo(QTabWidget):
    """Demo tab."""

    def __init__(self, parent=None, emphasized=False):
        super().__init__(parent)
        self.setProperty("emphasized", emphasized)
        self.tab1 = QWidget()
        self.tab1.setProperty("emphasized", emphasized)
        self.tab2 = QWidget()
        self.tab2.setProperty("emphasized", emphasized)

        self.addTab(self.tab1, "Tab 1")
        self.addTab(self.tab2, "Tab 2")
        layout = QFormLayout()
        layout.addRow("Height", QSpinBox())
        layout.addRow("Weight", QDoubleSpinBox())
        self.setTabText(0, "Tab 1")
        self.tab1.setLayout(layout)

        layout2 = QFormLayout()
        sex = QHBoxLayout()
        sex.addWidget(QRadioButton("Male"))
        sex.addWidget(QRadioButton("Female"))
        layout2.addRow(QLabel("Sex"), sex)
        layout2.addRow("Date of Birth", QLineEdit())
        self.setTabText(1, "Tab 2")
        self.tab2.setLayout(layout2)

        self.setWindowTitle("tab demo")


class QtSampleWidget(QWidget):
    """Widget that showcases many types of Qt widgets."""

    def __init__(self, emphasized: bool = False):
        super().__init__()
        self.setProperty("emphasized", emphasized)
        self.setStyleSheet(STYLESHEET)

        lay = QVBoxLayout()
        self.setLayout(lay)

        wid = QtReloadWidget(["qtreload"], self)
        lay.addWidget(wid)

        lay.addWidget(QPushButton("push button"))
        box = QComboBox()
        box.addItems(["a", "b", "c", "cd"])
        lay.addWidget(box)
        lay.addWidget(QFontComboBox())

        hbox = QHBoxLayout()
        chk = QCheckBox("tristate")
        chk.setToolTip("I am a tooltip")
        chk.setTristate(True)
        chk.setCheckState(Qt.CheckState.PartiallyChecked)
        chk3 = QCheckBox("checked")
        chk3.setChecked(True)
        hbox.addWidget(QCheckBox("unchecked"))
        hbox.addWidget(chk)
        hbox.addWidget(chk3)
        lay.addLayout(hbox)

        lay.addWidget(TabDemo(emphasized=emphasized))

        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setValue(50)
        lay.addWidget(sld)
        scroll = QScrollBar(Qt.Orientation.Horizontal)
        scroll.setValue(50)
        lay.addWidget(scroll)
        text = QTextEdit()
        text.setMaximumHeight(100)
        text.setHtml(blurb)
        lay.addWidget(text)
        lay.addWidget(QTimeEdit())
        edit = QLineEdit()
        edit.setPlaceholderText("LineEdit placeholder...")
        hlay = QHBoxLayout()
        lay.addWidget(edit)
        lay.addWidget(QLabel("label"))
        label = QLabel("SUCCESS")
        label.setObjectName("success")
        hlay.addWidget(label)
        label = QLabel("WARNING")
        label.setObjectName("warning")
        hlay.addWidget(label)
        label = QLabel("ACTIVE")
        label.setObjectName("active")
        hlay.addWidget(label)
        label = QLabel("STANDOUT")
        label.setObjectName("standout")
        hlay.addWidget(label)
        lay.addLayout(hlay)

        prog = QProgressBar()
        prog.setValue(50)
        lay.addWidget(prog)

        prog = QProgressBar()
        prog.setMaximum(0)
        lay.addWidget(prog)

        groupBox = QGroupBox("Exclusive Radio Buttons")
        radio1 = QRadioButton("&Radio button 1")
        radio2 = QRadioButton("R&adio button 2")
        radio3 = QRadioButton("Ra&dio button 3")
        radio1.setChecked(True)
        hbox = QHBoxLayout()
        hbox.addWidget(radio1)
        hbox.addWidget(radio2)
        hbox.addWidget(radio3)
        hbox.addStretch(1)
        groupBox.setLayout(hbox)


if __name__ == "__main__":  # pragma: no cover
    import sys

    app = QApplication(sys.argv)
    dlg = QtSampleWidget()
    dlg.show()

    sys.exit(app.exec_())
