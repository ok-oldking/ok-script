from ctypes import POINTER, Structure, Union, WinDLL, c_uint16, c_uint32, c_uint64
from ctypes.wintypes import (
    DWORD,
    HWND,
    LONG,
    LPCVOID,
    LPCWSTR,
    POINTL,
    RECTL,
    SHORT,
    WCHAR,
)
from enum import IntEnum

CCHDEVICENAME: int = 32

# https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-
ERROR_SUCCESS = 0
ERROR_INVALID_PARAMETER = 87
ERROR_NOT_SUPPORTED = 50
ERROR_ACCESS_DENIED = 5
ERROR_GEN_FAILURE = 31
ERROR_INSUFFICIENT_BUFFER = 122

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig
QDC_ONLY_ACTIVE_PATHS = 0x00000002

# https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-displayconfig_path_info
DISPLAYCONFIG_PATH_ACTIVE = 0x00000001

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaysettingsw
ENUM_CURRENT_SETTINGS = -1

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-changedisplaysettingsw
DM_PELSWIDTH = 524288
DM_PELSHEIGHT = 1048576
DM_DISPLAYFLAGS = 2097152
DM_DISPLAYFREQUENCY = 4194304

# DISPLAY_DEVICE.StateFlags
# https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-display_devicew
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 1
DISPLAY_DEVICE_PRIMARY_DEVICE = 4

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-changedisplaysettingsw
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1
DISP_CHANGE_FAILED = -1
DISP_CHANGE_BADMODE = -2
DISP_CHANGE_NOTUPDATED = -3
DISP_CHANGE_BADFLAGS = -4
DISP_CHANGE_BADPARAM = -5
DISP_CHANGE_BADDUALVIEW = -6


class LUID(Structure):
    _fields_ = [("lowPart", DWORD), ("highPart", LONG)]


class PATH_INFO_DUMMY_STRUCT_NAME(Structure):
    _fields_ = [
        ("cloneGroupId", c_uint32, 16),
        ("sourceModeInfoIdx", c_uint32, 16),
    ]


class PATH_INFO_DUMMY_UNION_NAME(Union):
    _fields_ = [("modeInfoIdx", c_uint32), ("dummyStruct", PATH_INFO_DUMMY_STRUCT_NAME)]


class DISPLAYCONFIG_PATH_SOURCE_INFO(Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", c_uint32),
        ("dummyUnion", PATH_INFO_DUMMY_UNION_NAME),
        ("statusFlags", c_uint32),
    ]


class DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY(IntEnum):
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_OTHER = 0
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_HD15 = 1
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_SVIDEO = 2
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_COMPOSITE_VIDEO = 3
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_COMPONENT_VIDEO = 4
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_DVI = 5
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_HDMI = 6
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_LVDS = 7
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_D_JPN = 8
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_SDI = 9
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_DISPLAYPORT_EXTERNAL = 10
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_DISPLAYPORT_EMBEDDED = 11
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_UDI_EXTERNAL = 12
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_UDI_EMBEDDED = 13
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_SDTVDONGLE = 14
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_MIRACAST = 15
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_INDIRECT_WIRED = 16
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_INDIRECT_VIRTUAL = 17
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_INTERNAL = 0x80000000
    DISPLAYCONFIG_OUTPUT_TECHNOLOGY_FORCE_UINT32 = 0xFFFFFFFF


class DISPLAYCONFIG_ROTATION(IntEnum):
    DISPLAYCONFIG_ROTATION_IDENTITY = 1
    DISPLAYCONFIG_ROTATION_ROTATE90 = 2
    DISPLAYCONFIG_ROTATION_ROTATE180 = 3
    DISPLAYCONFIG_ROTATION_ROTATE270 = 4
    DISPLAYCONFIG_ROTATION_FORCE_UINT32 = 0xFFFFFFFF


class DISPLAYCONFIG_SCALING(IntEnum):
    DISPLAYCONFIG_SCALING_IDENTITY = 1
    DISPLAYCONFIG_SCALING_CENTERED = 2
    DISPLAYCONFIG_SCALING_STRETCHED = 3
    DISPLAYCONFIG_SCALING_ASPECTRATIOCENTEREDMAX = 4
    DISPLAYCONFIG_SCALING_CUSTOM = 5
    DISPLAYCONFIG_SCALING_PREFERRED = 128


class DISPLAYCONFIG_RATIONAL(Structure):
    _fields_ = [("numerator", c_uint32), ("denominator", c_uint32)]


class DISPLAYCONFIG_SCANLINE_ORDERING(IntEnum):
    DISPLAYCONFIG_SCANLINE_ORDERING_UNSPECIFIED = 0
    DISPLAYCONFIG_SCANLINE_ORDERING_PROGRESSIVE = 1
    DISPLAYCONFIG_SCANLINE_ORDERING_INTERLACED = 2


class DISPLAYCONFIG_PATH_TARGET_INFO(Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", c_uint32),
        ("dummyUnion", PATH_INFO_DUMMY_UNION_NAME),
        ("outputTechnology", c_uint32),  # DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY
        ("rotation", c_uint32),  # DISPLAYCONFIG_ROTATION
        ("scaling", c_uint32),  # DISPLAYCONFIG_SCALING
        ("rational", DISPLAYCONFIG_RATIONAL),
        ("scanlineOrdering", c_uint32),  # DISPLAYCONFIG_SCANLINE_ORDERING
        ("targetAvailable", c_uint32),
        ("statusFlags", c_uint32),
    ]


class DISPLAYCONFIG_MODE_INFO_TYPE(IntEnum):
    DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE = 1
    DISPLAYCONFIG_MODE_INFO_TYPE_TARGET = 2
    DISPLAYCONFIG_MODE_INFO_TYPE_DESKTOP_IMAGE = 3
    DISPLAYCONFIG_MODE_INFO_TYPE_FORCE_UINT32 = 0xFFFFFFFF


class DISPLAYCONFIG_2DREGION(Structure):
    _fields_ = [("cx", c_uint32), ("cy", c_uint32)]


class DISPLAYCONFIG_DUMMY_STRUCT_NAME(Structure):
    _fields_ = [
        ("videoStandard", c_uint32, 16),
        ("vsyncFreqDivider", c_uint32, 6),
        ("reserved", c_uint32, 10),
    ]


class DISPLAYCONFIG_DUMMY_UNION_NAME(Union):
    _fields_ = [
        ("additionalSignalInfo", DISPLAYCONFIG_DUMMY_STRUCT_NAME),
        ("videoStandard", c_uint32),
    ]


class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(Structure):
    _fields_ = [
        ("pixelRate", c_uint64),
        ("hSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("vSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("activeSize", DISPLAYCONFIG_2DREGION),
        ("totalSize", DISPLAYCONFIG_2DREGION),
        ("dummyUnion", DISPLAYCONFIG_DUMMY_UNION_NAME),
        ("scanLineOrdering", c_uint32),  # DISPLAYCONFIG_SCANLINE_ORDERING
    ]


class DISPLAYCONFIG_TARGET_MODE(Structure):
    _fields_ = [("targetVideoSignalInfo", DISPLAYCONFIG_VIDEO_SIGNAL_INFO)]


class DISPLAYCONFIG_PIXELFORMAT(IntEnum):
    DISPLAYCONFIG_PIXELFORMAT_8BPP = 1
    DISPLAYCONFIG_PIXELFORMAT_16BPP = 2
    DISPLAYCONFIG_PIXELFORMAT_24BPP = 3
    DISPLAYCONFIG_PIXELFORMAT_32BPP = 4
    DISPLAYCONFIG_PIXELFORMAT_NONGDI = 5
    DISPLAYCONFIG_PIXELFORMAT_FORCE_UINT32 = 0xFFFFFFFF


class DISPLAYCONFIG_SOURCE_MODE(Structure):
    _fields_ = [
        ("width", c_uint32),
        ("height", c_uint32),
        ("pixelFormat", c_uint32),  # DISPLAYCONFIG_PIXELFORMAT
        ("position", POINTL),
    ]


class DISPLAYCONFIG_DESKTOP_IMAGE_INFO(Structure):
    _fields_ = [
        ("pathSourceSize", POINTL),
        ("desktopImageRegion", RECTL),
        ("desktopImageClip", RECTL),
    ]


class DISPLAYCONFIG_MODE_INFO_DUMMY_UNION_NAME(Union):
    _fields_ = [
        ("targetMode", DISPLAYCONFIG_TARGET_MODE),
        ("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
        ("desktopImageInfo", DISPLAYCONFIG_DESKTOP_IMAGE_INFO),
    ]


class DISPLAYCONFIG_MODE_INFO(Structure):
    _fields_ = [
        ("infoType", c_uint32),  # DISPLAYCONFIG_MODE_INFO_TYPE
        ("id", DWORD),
        ("adapterId", LUID),
        ("dummyUnion", DISPLAYCONFIG_MODE_INFO_DUMMY_UNION_NAME),
    ]


class DISPLAYCONFIG_PATH_INFO(Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", c_uint32),
    ]


class DISPLAYCONFIG_DEVICE_INFO_TYPE(IntEnum):
    DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
    DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME = 2
    DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_PREFERRED_MODE = 3
    DISPLAYCONFIG_DEVICE_INFO_GET_ADAPTER_NAME = 4
    DISPLAYCONFIG_DEVICE_INFO_SET_TARGET_PERSISTENCE = 5
    DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_BASE_TYPE = 6
    DISPLAYCONFIG_DEVICE_INFO_GET_SUPPORT_VIRTUAL_RESOLUTION = 7
    DISPLAYCONFIG_DEVICE_INFO_SET_SUPPORT_VIRTUAL_RESOLUTION = 8
    DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
    DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE = 10
    DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL = 11
    DISPLAYCONFIG_DEVICE_INFO_FORCE_UINT32 = 0xFFFFFFFF


class DISPLAYCONFIG_DEVICE_INFO_HEADER(Structure):
    _fields_ = [
        ("type", c_uint32),  # DISPLAYCONFIG_DEVICE_INFO_TYPE
        ("size", c_uint32),
        ("adapterId", LUID),
        ("id", c_uint32),
    ]


class DISPLAYCONFIG_COLOR_ENCODING(IntEnum):
    DISPLAYCONFIG_COLOR_ENCODING_RGB = 0
    DISPLAYCONFIG_COLOR_ENCODING_YCBCR444 = 1
    DISPLAYCONFIG_COLOR_ENCODING_YCBCR422 = 2
    DISPLAYCONFIG_COLOR_ENCODING_YCBCR420 = 3
    DISPLAYCONFIG_COLOR_ENCODING_INTENSITY = 4


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", c_uint32),
        ("colorEncoding", c_uint32),  # DISPLAYCONFIG_COLOR_ENCODING
        ("bitsPerColorChannel", c_uint32),
    ]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", WCHAR * CCHDEVICENAME),
    ]


class DISPLAYCONFIG_TARGET_DEVICE_NAME_FLAGS(Structure):
    _fields_ = [("value", c_uint32)]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("flags", DISPLAYCONFIG_TARGET_DEVICE_NAME_FLAGS),
        ("outputTechnology", c_uint32),  # DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY
        ("edidManufactureId", c_uint16),
        ("edidProductCodeId", c_uint16),
        ("connectorInstance", c_uint32),
        ("monitorFriendlyDeviceName", WCHAR * 64),
        ("monitorDevicePath", WCHAR * 128),
    ]


class DISPLAYCONFIG_ADAPTER_NAME(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("adapterDevicePath", WCHAR * 128),
    ]


class DEMOVEDW_DUMMY_STRUCT_NAME(Structure):
    _fields_ = [
        ("dmOrientation", SHORT),
        ("dmPaperSize", SHORT),
        ("dmPaperLength", SHORT),
        ("dmPaperWidth", SHORT),
        ("dmScale", SHORT),
        ("dmCopies", SHORT),
        ("dmDefaultSource", SHORT),
        ("dmPrintQuality", SHORT),
    ]


class DEVMODEW_DUMMY_STRUCT_NAME2(Structure):
    _fields_ = [
        ("dmPosition", POINTL),
        ("dmDisplayOrientation", DWORD),
        ("dmDisplayFixedOutput", DWORD),
    ]


class DEVMODEW_DUMMY_UNION_NAME(Union):
    _fields_ = [
        ("dummyStruct", DEMOVEDW_DUMMY_STRUCT_NAME),
        ("dmPosition", POINTL),
        ("dummyStruct2", DEVMODEW_DUMMY_STRUCT_NAME2),
    ]


class DEVMODEW_DUMMY_UNION_NAME2(Union):
    _fields_ = [("dmDisplayFlags", DWORD), ("dmNup", DWORD)]


class DEVMODEW(Structure):
    _fields_ = [
        ("dmDeviceName", WCHAR * CCHDEVICENAME),
        ("dmSpecVersion", SHORT),
        ("dmDriverVersion", SHORT),
        ("dmSize", SHORT),
        ("dmDriverExtra", SHORT),
        ("dmFields", DWORD),
        ("dmDummyUnion", DEVMODEW_DUMMY_UNION_NAME),
        ("dmColor", SHORT),
        ("dmDuplex", SHORT),
        ("dmYResolution", SHORT),
        ("dmTTOption", SHORT),
        ("dmCollate", SHORT),
        ("dmFormName", WCHAR * CCHDEVICENAME),
        ("dmLogPixels", SHORT),
        ("dmBitsPerPel", DWORD),
        ("dmPelsWidth", DWORD),
        ("dmPelsHeight", DWORD),
        ("dmDummyUnion2", DEVMODEW_DUMMY_UNION_NAME2),
        ("dmDisplayFrequency", DWORD),
        ("dmICMMethod", DWORD),
        ("dmICMIntent", DWORD),
        ("dmMediaType", DWORD),
        ("dmDitherType", DWORD),
        ("dmReserved1", DWORD),
        ("dmReserved2", DWORD),
        ("dmPanningWidth", DWORD),
        ("dmPanningHeight", DWORD),
    ]


class DISPLAY_DEVICEW(Structure):
    _fields_ = [
        ("cb", DWORD),
        ("DeviceName", WCHAR * 32),
        ("DeviceString", WCHAR * 128),
        ("StateFlags", DWORD),
        ("DeviceID", WCHAR * 128),
        ("DeviceKey", WCHAR * 128),
    ]


class DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE(Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("enableAdvancedColor", c_uint32),
    ]


# Imported API functions
user32DLL = WinDLL("user32")

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-changedisplaysettingsexw
ChangeDisplaySettingsExW = user32DLL.ChangeDisplaySettingsExW
ChangeDisplaySettingsExW.restype = LONG
ChangeDisplaySettingsExW.argtypes = [LPCWSTR, POINTER(DEVMODEW), HWND, DWORD, LPCVOID]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaysettingsw
EnumDisplaySettingsW = user32DLL.EnumDisplaySettingsW
EnumDisplaySettingsW.restype = LONG
EnumDisplaySettingsW.argtypes = [LPCWSTR, DWORD, POINTER(DEVMODEW)]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaydevicesw
EnumDisplayDevicesW = user32DLL.EnumDisplayDevicesW
EnumDisplayDevicesW.restype = LONG
EnumDisplayDevicesW.argtypes = [LPCWSTR, DWORD, POINTER(DISPLAY_DEVICEW)]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-displayconfiggetdeviceinfo
DisplayConfigGetDeviceInfo = user32DLL.DisplayConfigGetDeviceInfo
DisplayConfigGetDeviceInfo.restype = LONG
DisplayConfigGetDeviceInfo.argtypes = [POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-displayconfigsetdeviceinfo
DisplayConfigSetDeviceInfo = user32DLL.DisplayConfigSetDeviceInfo
DisplayConfigSetDeviceInfo.restype = LONG
DisplayConfigSetDeviceInfo.argtypes = [POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdisplayconfigbuffersizes
GetDisplayConfigBufferSizes = user32DLL.GetDisplayConfigBufferSizes
GetDisplayConfigBufferSizes.restype = LONG
GetDisplayConfigBufferSizes.argtypes = [c_uint32, POINTER(c_uint32), POINTER(c_uint32)]

# https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-querydisplayconfig
QueryDisplayConfig = user32DLL.QueryDisplayConfig
QueryDisplayConfig.restype = LONG
QueryDisplayConfig.argtypes = [
    c_uint32,
    POINTER(c_uint32),
    POINTER(DISPLAYCONFIG_PATH_INFO),
    POINTER(c_uint32),
    POINTER(DISPLAYCONFIG_MODE_INFO),
    POINTER(c_uint32),
]
