from PySide6.QtWidgets import QTextEdit
from qfluentwidgets import TextEdit, PushButton

import ok.gui
from ok.capture.windows.dump import dump_threads
from ok.gui.widget.Tab import Tab


class AboutTab(Tab):
    def __init__(self, text=""):
        super().__init__()
        # Create a QTextEdit instance
        text_edit = TextEdit()
        text_edit.setHtml(text)
        text_edit.setReadOnly(True)

        # Set the layout on the widget
        self.addWidget(text_edit)
        if ok.gui.ok.debug:
            dump_button = PushButton(self.tr("Dump Threads(HotKey:Ctrl+Alt+D)"))
            dump_button.clicked.connect(dump_threads)
            self.addWidget(dump_button)


