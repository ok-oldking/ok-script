from PySide6.QtWidgets import QLabel

ROLES = ("display", "title", "subtitle", "body", "strong", "secondary", "caption", "section", "mono", "kbd", "chip")


class Label(QLabel):
    """A QLabel whose typography comes from its ``role``.

    ``section`` labels are shown upper-case, as stylesheets cannot transform
    text.
    """

    def __init__(self, text: str = "", role: str = "body", parent=None, word_wrap: bool = False):
        super().__init__(parent)
        if role not in ROLES:
            raise ValueError(f"unknown label role: {role!r}")
        self._role = role
        self.setProperty("role", role)
        self.setWordWrap(word_wrap)
        self.setText(text)

    @property
    def role(self) -> str:
        return self._role

    def setText(self, text: str) -> None:
        super().setText(text.upper() if self._role == "section" else text)
