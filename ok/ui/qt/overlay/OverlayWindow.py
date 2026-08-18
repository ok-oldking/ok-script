"""Compatibility import for the framework-independent native overlay.

The overlay is intentionally no longer a QWidget: its click-through layered
Win32 window is shared by Qt and the headless web/Tauri runtime.
"""

from ok.ui.overlay.win32_gdi import GdiCanvas, Win32GdiOverlay

OverlayWindow = Win32GdiOverlay

__all__ = ["GdiCanvas", "OverlayWindow", "Win32GdiOverlay"]
