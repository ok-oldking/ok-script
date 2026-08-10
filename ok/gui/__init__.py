"""Compatibility namespace for the Qt UI moved to :mod:`ok.ui.qt`.

New code should import ``ok.ui.qt``.  Keeping this lightweight namespace lets
existing applications migrate without importing PySide during headless use.
"""

from pathlib import Path

_compat = Path(__file__).resolve().parent
__path__ = [str(_compat), str(_compat.parent / "ui" / "qt")]
