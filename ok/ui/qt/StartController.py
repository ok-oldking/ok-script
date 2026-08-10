"""Module alias for the UI-independent start controller."""

import sys

from ok.core import start_controller as _core

sys.modules[__name__] = _core
