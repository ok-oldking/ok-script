from PySide6.QtWidgets import QTextEdit

from ok.gui.widget.Tab import Tab


class AboutTab(Tab):
    def __init__(self, text=""):
        super().__init__()
        # Create a QTextEdit instance
        text_edit = QTextEdit()
        text_edit.setHtml(text)
        text_edit.setReadOnly(True)

        # Set the layout on the widget
        self.addWidget(text_edit)
