from ctypes import byref, sizeof

from ok.display.custom_types import DisplayAdapter, DisplayAdapterException, DisplayMode
from ok.display.windows_types import (
    DEVMODEW,
    DISP_CHANGE_BADDUALVIEW,
    DISP_CHANGE_BADFLAGS,
    DISP_CHANGE_BADMODE,
    DISP_CHANGE_BADPARAM,
    DISP_CHANGE_FAILED,
    DISP_CHANGE_NOTUPDATED,
    DISP_CHANGE_RESTART,
    DISP_CHANGE_SUCCESSFUL,
    DISPLAY_DEVICE_ATTACHED_TO_DESKTOP,
    DISPLAY_DEVICE_PRIMARY_DEVICE,
    DISPLAY_DEVICEW,
    DM_DISPLAYFREQUENCY,
    DM_PELSHEIGHT,
    DM_PELSWIDTH,
    ENUM_CURRENT_SETTINGS,
    ChangeDisplaySettingsExW,
    EnumDisplayDevicesW,
    EnumDisplaySettingsW,
)


def is_attached_to_desktop(adapter: DISPLAY_DEVICEW) -> bool:
    state_flags: int = adapter.StateFlags

    return (
            state_flags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
            == DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
    )


def is_primary_device(adapter: DISPLAY_DEVICEW) -> bool:
    state_flags: int = adapter.StateFlags

    return state_flags & DISPLAY_DEVICE_PRIMARY_DEVICE == DISPLAY_DEVICE_PRIMARY_DEVICE


def get_all_display_adapters() -> list[DisplayAdapter]:
    adapters: list[DisplayAdapter] = []

    # This will hold display device information on every iteration of the loop
    display_device = DISPLAY_DEVICEW()
    display_device.cb = sizeof(DISPLAY_DEVICEW)
    display_device.StateFlags = DISPLAY_DEVICE_ATTACHED_TO_DESKTOP

    try:
        # Tell Windows to cache display device information before we start looping
        EnumDisplayDevicesW(None, 0, byref(display_device))
    except OSError:
        raise DisplayAdapterException("Failed to get list of available display devices")

    index_of_current_adapter: int = 0
    finished_searching_for_devices: bool = False

    while not finished_searching_for_devices:
        result: int = EnumDisplayDevicesW(
            None, index_of_current_adapter, byref(display_device)
        )

        if result == 0:
            finished_searching_for_devices = True
        else:
            try:
                display_adapter = DisplayAdapter()
                display_adapter.identifier = str(display_device.DeviceName)
                display_adapter.display_name = str(display_device.DeviceString)
                display_adapter.active_mode = get_active_display_mode_for_adapter(
                    display_device
                )
                display_adapter.available_modes = (
                    get_all_available_display_modes_for_adapter(display_device)
                )
                display_adapter.is_attached = is_attached_to_desktop(display_device)
                display_adapter.is_primary = is_primary_device(display_device)

                adapters.append(display_adapter)
            except DisplayAdapterException:
                pass
            finally:
                index_of_current_adapter += 1

    return adapters


def get_all_available_display_modes_for_adapter(
        adapter: DISPLAY_DEVICEW,
) -> list[DisplayMode]:
    identifier: str = adapter.DeviceName
    display_modes: list[DisplayMode] = []

    # This will store the display mode information on every loop iteration
    devmodew: DEVMODEW = DEVMODEW()
    devmodew.dmSize = sizeof(DEVMODEW)

    try:
        # Tell Windows to cache display mode information before we start looping
        result: int = EnumDisplaySettingsW(identifier, 0, devmodew)

        if result == 0:
            raise DisplayAdapterException(
                f"Failed to get available modes for {identifier}. Failed with result {result}"
            )

    except OSError as e:
        raise DisplayAdapterException(
            f"Failed to get available modes for {identifier}. Failed with error {str(e)}"
        )

    index_of_current_mode: int = 1
    finished_getting_modes: bool = False

    while not finished_getting_modes:
        try:
            result: int = EnumDisplaySettingsW(
                identifier, index_of_current_mode, byref(devmodew)
            )

            if result == 0:
                finished_getting_modes = True
            else:
                display_mode = DisplayMode(
                    devmodew.dmPelsWidth,
                    devmodew.dmPelsHeight,
                    devmodew.dmDisplayFrequency,
                )
                display_modes.append(display_mode)

                index_of_current_mode += 1
        except OSError:
            finished_getting_modes = True

    return display_modes


def get_active_display_mode_for_adapter(adapter: DISPLAY_DEVICEW) -> DisplayMode:
    identifier = adapter.DeviceName

    try:
        display_modew = DEVMODEW()
        display_modew.dmSize = sizeof(DEVMODEW)

        result: int = EnumDisplaySettingsW(
            identifier, ENUM_CURRENT_SETTINGS, byref(display_modew)
        )

        if result == 0:
            raise DisplayAdapterException(
                f"Failed to get active mode for {identifier}. Failed with result {result}"
            )

        return DisplayMode(
            display_modew.dmPelsWidth,
            display_modew.dmPelsHeight,
            display_modew.dmDisplayFrequency,
        )
    except OSError as e:
        raise DisplayAdapterException(
            f"Failed to get active mode for {identifier}. Failed with error {str(e)}"
        )


def set_display_mode_for_device(display_mode: DisplayMode, device_identifier: str):
    if device_identifier is None:
        raise DisplayAdapterException("Device identifier cannot be empty")

    if display_mode is None:
        raise DisplayAdapterException("Display settings cannot be empty")

    devmodew = DEVMODEW()
    devmodew.dmDeviceName = device_identifier
    devmodew.dmSize = sizeof(DEVMODEW)
    devmodew.dmPelsWidth = display_mode.width
    devmodew.dmPelsHeight = display_mode.height
    devmodew.dmDisplayFrequency = display_mode.refresh
    devmodew.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY

    try:
        result: int = ChangeDisplaySettingsExW(
            device_identifier, byref(devmodew), None, 0, None
        )

        if result == DISP_CHANGE_SUCCESSFUL:
            return
        elif result == DISP_CHANGE_RESTART:
            raise DisplayAdapterException(
                "The computer must be restarted for the graphics mode to work"
            )
        elif result == DISP_CHANGE_BADFLAGS:
            raise DisplayAdapterException("An invalid set of flags was passed in")
        elif result == DISP_CHANGE_BADMODE:
            raise DisplayAdapterException("The graphics mode is not supported")
        elif result == DISP_CHANGE_BADPARAM:
            raise DisplayAdapterException("An invalid parameter was passed in")
        elif result == DISP_CHANGE_FAILED:
            raise DisplayAdapterException(
                "The display driver failed the specified graphics mode"
            )
        elif result == DISP_CHANGE_NOTUPDATED:
            raise DisplayAdapterException("Unable to write settings to the registry")
        elif result == DISP_CHANGE_BADDUALVIEW:
            raise DisplayAdapterException(
                "The settings change was unsuccessful because the system is DualView capable"
            )
        else:
            raise DisplayAdapterException("An unknown error occurred")

    except OSError as e:
        raise DisplayAdapterException(
            f"Failed to change display settings. Failed with error {str(e)}"
        )
