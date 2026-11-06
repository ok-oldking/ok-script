from PySide6.QtWidgets import QVBoxLayout, QWidget


class LazyPage(QWidget):
    """Stands in for a page in the main stack and builds it on first use.

    Use :meth:`page` to reach the real page; it is built if needed.
    """

    def __init__(self, factory, parent=None):
        super().__init__(parent)
        self._factory = factory
        self._page = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def is_built(self) -> bool:
        return self._page is not None

    def page(self) -> QWidget:
        if self._page is None:
            self._page = self._factory()
            self._factory = None
            self._layout.addWidget(self._page)
        return self._page

    def dispose(self) -> None:
        if self._page is None:
            return
        cleanup = getattr(self._page, 'dispose', None) or getattr(self._page, 'stop_worker', None)
        if callable(cleanup):
            cleanup()
