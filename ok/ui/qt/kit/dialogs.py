from PySide6.QtCore import QEvent, QEventLoop, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme


class DialogPanel(QFrame):
    """The card that holds a dialog's content."""


class Dialog(QWidget):
    """A modal dialog drawn inside its window over a dimmed backdrop.

    Put custom content in :attr:`body`. :meth:`exec` blocks until the dialog
    is accepted (OK, Enter) or rejected (Cancel, Esc, backdrop click) and
    returns ``True`` when accepted.
    """

    accepted = Signal()
    rejected = Signal()

    def __init__(self, parent: QWidget, title: str, message: str = None, ok_text: str = None,
                 cancel_text: str = None, danger: bool = False, width: int = 440):
        window = parent.window()
        super().__init__(window)
        self._result = False
        self._loop = None
        # Key of the button that closed the dialog: "ok", "cancel" or an add_button key.
        self.choice = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.panel = DialogPanel(self)
        self.panel.setFixedWidth(width)
        self.title_label = Label(title, "subtitle", self.panel, word_wrap=True)
        self.message_label = Label(message or "", "secondary", self.panel, word_wrap=True)
        self.message_label.setVisible(bool(message))
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 4, 0, 0)
        self.body.setSpacing(10)

        self.cancel_button = Button(cancel_text or self.tr("Cancel"))
        self.ok_button = Button(ok_text or self.tr("OK"), variant="danger" if danger else "primary")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.ok_button)
        self._buttons = buttons

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)
        layout.addLayout(self.body)
        layout.addSpacing(12)
        layout.addLayout(buttons)

        window.installEventFilter(self)
        theme.install(self)
        self.hide()

    def set_cancel_visible(self, visible: bool) -> None:
        self.cancel_button.setVisible(visible)

    def add_button(self, key: str, text: str, variant: str = "secondary") -> Button:
        """Add a button left of Cancel; clicking it rejects with ``choice == key``."""

        button = Button(text, variant=variant, parent=self.panel)
        button.clicked.connect(lambda: self._finish(False, key))
        self._buttons.insertWidget(1, button)
        return button

    def validate(self) -> bool:
        """Override to keep the dialog open when its input is not acceptable."""
        return True

    def result(self) -> bool:
        return self._result

    def open(self) -> None:
        self._result = False
        self.choice = None
        self._fit()
        self.show()
        self.raise_()
        self.ok_button.setFocus()

    def exec(self) -> bool:
        self.open()
        self._loop = QEventLoop(self)
        self._loop.exec()
        self._loop = None
        return self._result

    def accept(self) -> None:
        if self.validate():
            self._finish(True, "ok")

    def reject(self) -> None:
        self._finish(False, "cancel")

    def _finish(self, result: bool, choice: str = None) -> None:
        if not self.isVisible() and self._loop is None:
            return
        self._result = result
        self.choice = choice
        self.hide()
        (self.accepted if result else self.rejected).emit()
        if self._loop is not None:
            self._loop.quit()

    def _fit(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.panel.adjustSize()
        self.panel.move((self.width() - self.panel.width()) // 2, max(24, (self.height() - self.panel.height()) // 2))

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._fit()
        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.cancel_button.isVisible():
                self.reject()
            else:
                self.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # A disabled OK means the dialog is not ready to be accepted.
            if self.ok_button.isEnabled():
                self.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()) and self.cancel_button.isVisible():
            self.reject()
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.color("scrim"))


def confirm(parent: QWidget, title: str, message: str = None, ok_text: str = None, danger: bool = False) -> bool:
    """Ask a yes/no question in ``parent``'s window and wait for the answer."""

    dialog = Dialog(parent, title, message, ok_text=ok_text, danger=danger)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
