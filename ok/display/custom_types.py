from typing import Optional

from ok.display.windows_types import (
    DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_MODE_INFO,
)


class DisplayMode:
    def __init__(self, width: int, height: int, refresh: int):
        self.width: int = width
        self.height: int = height
        self.refresh: int = refresh

    def __str__(self):
        return (
                str(self.width) + "x" + str(self.height) + " @ " + str(self.refresh) + "Hz"
        )


class DisplayAdapter:
    def __init__(
            self,
            identifier: str = "",
            display_name: str = "",
            active_mode: Optional[DisplayMode] = None,
            available_modes: Optional[list[DisplayMode]] = None,
            is_attached: bool = False,
            is_primary: bool = False,
    ):
        self.identifier: str = identifier
        self.display_name: str = display_name
        self.active_mode: Optional[DisplayMode] = active_mode
        self.available_modes: Optional[list[DisplayMode]] = available_modes
        self.is_attached: bool = is_attached
        self.is_primary: bool = is_primary


class DisplayMonitor:
    def __init__(
            self,
            name: str = "",
            adapter: DisplayAdapter = DisplayAdapter(),
            mode_info: Optional[DISPLAYCONFIG_MODE_INFO] = None,
            color_info: Optional[DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO] = None,
    ):
        self.name: str = name
        self.adapter: DisplayAdapter = adapter
        self.mode_info: Optional[DISPLAYCONFIG_MODE_INFO] = mode_info
        self.color_info: Optional[DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO] = color_info

    def identifier(self) -> str:
        return self.adapter.identifier

    def active_mode(self) -> Optional[DisplayMode]:
        return self.adapter.active_mode

    def is_primary(self) -> bool:
        return self.adapter.is_primary

    def is_attached(self) -> bool:
        return self.adapter.is_attached

    def is_hdr_supported(self) -> bool:
        if self.color_info is None:
            return False

        return self.color_info.value & 0x1 == 0x1

    def is_hdr_enabled(self) -> bool:
        if self.color_info is None:
            return False

        return self.color_info.value & 0x2 == 0x2


class DisplayMonitorException(Exception):
    pass


class PrimaryMonitorException(Exception):
    pass


class HdrException(Exception):
    pass


class DisplayAdapterException(Exception):
    pass
