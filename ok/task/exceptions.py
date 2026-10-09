class TaskDisabledException(Exception):
    pass


class CannotFindException(Exception):
    pass


class FinishedException(Exception):
    pass


class WaitFailedException(Exception):
    pass


class CaptureException(Exception):
    pass


class CaptureBusyException(Exception):
    """A capture resource is temporarily owned by another caller.

    This is normal backpressure (a concurrent frame request or lifecycle
    refresh), not a capture failure. Callers should retry, and it must never
    disqualify or close the underlying capture method.
    """
    pass


class HotkeyConfigException(Exception):
    def __init__(self, key):
        self.key = key
        super().__init__(f"{key} is invalid, please check the hotkey config!")
