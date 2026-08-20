"""Qt main-thread scheduler for core events."""

import inspect
import weakref

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot
from shiboken6 import isValid

from ok.core.events import set_event_dispatcher


_NO_LIMIT = object()
_MISSING = object()


def _positional_limit(callback):
    """Return the positional argument limit used by Qt-compatible slots."""
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return _NO_LIMIT
    limit = 0
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            return _NO_LIMIT
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            limit += 1
    return limit


class QtEventDispatcher(QObject):
    requested = Signal(object, object, object)

    def __init__(self):
        super().__init__()
        # Subscribers are often bound QObject methods.  A regular dict would
        # keep their Python wrappers alive after the UI releases them.
        self._positional_limits = weakref.WeakKeyDictionary()
        self.requested.connect(self._invoke)

    def _invoke_callback(self, callback, args, kwargs):
        # The framework-neutral event bus can have callbacks queued while a Qt
        # widget is being torn down.  Unlike a native Qt signal, it cannot
        # automatically discard a bound method when the underlying C++ QObject
        # has already been deleted.
        owner = getattr(callback, "__self__", None)
        if isinstance(owner, QObject) and not isValid(owner):
            return
        try:
            limit = self._positional_limits.get(callback, _MISSING)
            if limit is _MISSING:
                limit = _positional_limit(callback)
                self._positional_limits[callback] = limit
        except TypeError:
            # A callable object may be unhashable; inspecting it per call is
            # still preferable to changing its invocation semantics.
            limit = _positional_limit(callback)
        if limit is not _NO_LIMIT and len(args) > limit:
            args = args[:limit]
        callback(*args, **kwargs)

    def dispatch(self, callback, args, kwargs):
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() is app.thread():
            self._invoke_callback(callback, args, kwargs)
        else:
            self.requested.emit(callback, args, kwargs)

    @Slot(object, object, object)
    def _invoke(self, callback, args, kwargs):
        self._invoke_callback(callback, args, kwargs)


_dispatcher = None


def install_qt_event_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = QtEventDispatcher()
    set_event_dispatcher(_dispatcher.dispatch)
    return _dispatcher
