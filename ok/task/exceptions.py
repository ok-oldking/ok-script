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


class HotkeyConfigException(Exception):
    def __init__(self, key):
        self.key = key
        super().__init__(f"{key} is invalid, please check the hotkey config!")
