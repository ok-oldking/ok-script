from ctypes import byref, c_ulong, sizeof

from ok.display.custom_types import (
    DisplayMonitor,
    DisplayMonitorException,
    PrimaryMonitorException,
)
from ok.display.display_adapters import DisplayAdapter, get_all_display_adapters
from ok.display.windows_types import (
    DISPLAYCONFIG_ADAPTER_NAME,
    DISPLAYCONFIG_DEVICE_INFO_TYPE,
    DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_MODE_INFO,
    DISPLAYCONFIG_PATH_INFO,
    DISPLAYCONFIG_PATH_SOURCE_INFO,
    DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE,
    DISPLAYCONFIG_SOURCE_DEVICE_NAME,
    DISPLAYCONFIG_TARGET_DEVICE_NAME,
    ERROR_SUCCESS,
    QDC_ONLY_ACTIVE_PATHS,
    DisplayConfigGetDeviceInfo,
    DisplayConfigSetDeviceInfo,
    GetDisplayConfigBufferSizes,
    QueryDisplayConfig,
)


def get_adapter_name(mode_info: DISPLAYCONFIG_MODE_INFO) -> str:
    adapter_info = DISPLAYCONFIG_ADAPTER_NAME()
    adapter_info.header.type = (
        DISPLAYCONFIG_DEVICE_INFO_TYPE.DISPLAYCONFIG_DEVICE_INFO_GET_ADAPTER_NAME
    )
    adapter_info.header.size = sizeof(DISPLAYCONFIG_ADAPTER_NAME)
    adapter_info.header.adapterId = mode_info.adapterId

    try:
        result: int = DisplayConfigGetDeviceInfo(byref(adapter_info.header))

        if result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to get adapter name with result {result}"
            )

        return str(adapter_info.adapterDevicePath)
    except OSError as e:
        raise DisplayMonitorException(f"Failed to get adapter name with error {e}")


def get_monitor_source_name(path_source_info: DISPLAYCONFIG_PATH_SOURCE_INFO) -> str:
    device_info = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
    device_info.header.type = (
        DISPLAYCONFIG_DEVICE_INFO_TYPE.DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
    )
    device_info.header.size = sizeof(DISPLAYCONFIG_SOURCE_DEVICE_NAME)
    device_info.header.adapterId = path_source_info.adapterId
    device_info.header.id = path_source_info.id

    try:
        result: int = DisplayConfigGetDeviceInfo(byref(device_info.header))

        if result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to get monitor source with result {result}"
            )

        return str(device_info.viewGdiDeviceName)

    except OSError as e:
        raise DisplayMonitorException(f"Failed to get monitor source with error {e}")


def get_monitor_name(mode_info: DISPLAYCONFIG_MODE_INFO) -> str:
    device_info = DISPLAYCONFIG_TARGET_DEVICE_NAME()
    device_info.header.type = (
        DISPLAYCONFIG_DEVICE_INFO_TYPE.DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
    )
    device_info.header.size = sizeof(DISPLAYCONFIG_TARGET_DEVICE_NAME)
    device_info.header.adapterId = mode_info.adapterId
    device_info.header.id = mode_info.id

    try:
        result: int = DisplayConfigGetDeviceInfo(byref(device_info.header))

        if result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to get monitor name with result {result}"
            )

        return str(device_info.monitorFriendlyDeviceName)

    except OSError as e:
        raise DisplayMonitorException(f"Failed to get monitor name with error {e}")


def get_monitor_color_info(
        mode_info: DISPLAYCONFIG_MODE_INFO,
) -> DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO:
    color_info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
    color_info.header.type = (
        DISPLAYCONFIG_DEVICE_INFO_TYPE.DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
    )
    color_info.header.size = sizeof(DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO)
    color_info.header.adapterId.highPart = mode_info.adapterId.highPart
    color_info.header.adapterId.lowPart = mode_info.adapterId.lowPart
    color_info.header.id = mode_info.id

    try:
        result: int = DisplayConfigGetDeviceInfo(byref(color_info.header))

        if result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to get monitor color info with result {result}"
            )

        return color_info

    except OSError as e:
        raise DisplayMonitorException(
            f"Failed to get monitor color info with error {e}"
        )


def set_hdr_state_for_monitor(enabled: bool, monitor: DisplayMonitor):
    if monitor.mode_info is None:
        raise DisplayMonitorException(
            "Cannot change HDR state for monitor without mode info"
        )

    mode_info: DISPLAYCONFIG_MODE_INFO = monitor.mode_info

    color_state = DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE()
    color_state.header.type = DISPLAYCONFIG_DEVICE_INFO_TYPE.DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE
    color_state.header.size = sizeof(DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE)
    color_state.header.adapterId.highPart = mode_info.adapterId.highPart
    color_state.header.adapterId.lowPart = mode_info.adapterId.lowPart
    color_state.header.id = mode_info.id
    color_state.enableAdvancedColor = enabled

    try:
        result: int = DisplayConfigSetDeviceInfo(byref(color_state.header))

        if result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to change HDR state  with result {result}"
            )

    except OSError as e:
        raise DisplayMonitorException(f"Failed to change HDR state with error {e}")


def get_primary_monitor(monitors: list[DisplayMonitor]) -> DisplayMonitor:
    for monitor in monitors:
        if monitor.is_primary():
            if monitor.identifier() is None:
                raise PrimaryMonitorException("Primary monitor has no identifier")
            else:
                return monitor

    raise PrimaryMonitorException("Primary monitor not found")


def get_all_display_monitors() -> list[DisplayMonitor]:
    display_adapters: list[DisplayAdapter] = get_all_display_adapters()
    connected_monitors: list[DisplayMonitor] = []

    # Get display config buffer sizes
    number_of_active_display_paths = c_ulong()
    number_of_active_display_modes = c_ulong()

    try:
        config_buffers_result: int = GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS,
            byref(number_of_active_display_paths),
            byref(number_of_active_display_modes),
        )

        # We don't want to continue if we don't know the buffer sizes
        if config_buffers_result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to determine monitor config buffer size with result {config_buffers_result}"
            )

    except OSError as e:
        raise DisplayMonitorException(
            f"Failed to determine monitor config buffer size with error {e}"
        )

    # Pre-allocate space to store the display paths and modes based on the previously retrieved buffer sizes
    paths = (DISPLAYCONFIG_PATH_INFO * number_of_active_display_paths.value)()
    modes = (DISPLAYCONFIG_MODE_INFO * number_of_active_display_modes.value)()

    try:
        # Get the display config and store it in the pre-allocated space (paths and modes)
        display_config_result: int = QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            byref(number_of_active_display_paths),
            byref(paths[0]),
            byref(number_of_active_display_modes),
            byref(modes[0]),
            None,
        )

        # We don't want to continue if we don't know the display config
        if display_config_result != ERROR_SUCCESS:
            raise DisplayMonitorException(
                f"Failed to get display config with result {display_config_result}"
            )

    except OSError as e:
        raise DisplayMonitorException(f"Failed to get display config with error {e}")

    # For every path we retrieve, we identify the target (a monitor) and the source (a display adapter), and pair
    # them together to create what we call a DisplayMonitor object
    for i in range(number_of_active_display_paths.value):
        path: DISPLAYCONFIG_PATH_INFO = paths[i]

        for j in range(number_of_active_display_modes.value):
            mode_info: DISPLAYCONFIG_MODE_INFO = modes[j]

            if mode_info.id != path.targetInfo.id:
                continue

            try:
                monitor = DisplayMonitor()
                monitor.name = get_monitor_name(mode_info)

                monitor_source_name = get_monitor_source_name(path.sourceInfo)
                for adapter in display_adapters:
                    if adapter.identifier == monitor_source_name:
                        monitor.adapter = adapter

                monitor.mode_info = mode_info
                monitor.color_info = get_monitor_color_info(mode_info)

                connected_monitors.append(monitor)

            except DisplayMonitorException as e:
                raise DisplayMonitorException(
                    f"Failed to get settings and other information with error {e}"
                )

    return connected_monitors
