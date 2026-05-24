import ctypes
import importlib
import importlib.util
import os
import re
import struct
import time
from contextlib import contextmanager
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, Iterable, List, Optional, Tuple

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

NVAPI_OK = 0
NVAPI_SETTING_NOT_FOUND = -160
NVAPI_NVIDIA_DEVICE_NOT_FOUND = -6
NVAPI_UNICODE_STRING_MAX = 2048

# NVIDIA Profile Inspector / NVAPI (issues #149, #181, #327; CustomSettingNames.xml)
NV_DRS_CLASSIC_SHARPENING_ENABLE_ID = 0x00598928  # Sharpening Filter - Enabled
NV_DRS_IMAGE_SHARPENING_IDS = (NV_DRS_CLASSIC_SHARPENING_ENABLE_ID,)
NV_DRS_RTX_DYNAMIC_VIBRANCE_ENABLE_ID = 0x00980880
NV_DRS_RTX_HDR_ENABLE_ID = 0x00DD48FB  # RTX HDR - Enable
NV_DRS_RTX_HDR_DRIVER_FLAGS_ID = 0x00432F84  # RTX HDR - Driver Flags (non-zero => driver HDR path)

NVAPI_DRS_GET_CURRENT_GLOBAL_PROFILE = 0x617BFF9F
NVAPI_DRS_FIND_PROFILE_BY_NAME = 0x7E4A9A0B
NVAPI_DRS_ENUM_PROFILES = 0xBC371EE0
NVAPI_DRS_GET_PROFILE_INFO = 0x61CD6FD6

ERROR_SUCCESS = 0
ERROR_INSUFFICIENT_BUFFER = 122
QDC_ONLY_ACTIVE_PATHS = 0x00000002
DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
CCHDEVICENAME = 32
MONITOR_DEFAULTTONEAREST = 2
NVIDIA_FILTER_PROFILE_LOG_MAX_AGE_SECONDS = 300
NVIDIA_OVERLAY_LOG_TAIL_BYTES = 2 * 1024 * 1024
NVIDIA_OVERLAY_TARGET_CONTEXT_LINES = 300

NV_DRS_DB_PATHS = (
    os.path.join(os.environ.get("ProgramData", ""), "NVIDIA Corporation", "Drs", "nvdrsdb0.bin"),
    os.path.join(os.environ.get("ProgramData", ""), "NVIDIA Corporation", "Drs", "nvdrsdb1.bin"),
)

_NVAPI_INIT_UNAVAILABLE_MESSAGE: Optional[str] = None
_NVAPI_INIT_UNAVAILABLE_LOGGED = False


@dataclass(frozen=True)
class GpuDriverPostProcessing:
    vendor: str
    feature: str
    enabled: bool
    detail: Optional[str] = None


class NVDRS_SETTING_UNION(ctypes.Structure):
    _pack_ = 8
    _fields_ = [("rawData", ctypes.c_ubyte * 4100)]


class NVDRS_SETTING(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("settingName", ctypes.c_wchar * NVAPI_UNICODE_STRING_MAX),
        ("settingId", ctypes.c_uint32),
        ("settingType", ctypes.c_int),
        ("settingLocation", ctypes.c_int),
        ("isCurrentPredefined", ctypes.c_uint32),
        ("isPredefinedValid", ctypes.c_uint32),
        ("predefinedValue", NVDRS_SETTING_UNION),
        ("currentValue", NVDRS_SETTING_UNION),
    ]


class NVDRS_PROFILE(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("profileName", ctypes.c_wchar * NVAPI_UNICODE_STRING_MAX),
        ("gpuSupport", ctypes.c_uint32),
        ("isPredefined", ctypes.c_uint32),
        ("numOfApps", ctypes.c_uint32),
        ("numOfSettings", ctypes.c_uint32),
    ]


NVDRS_SETTING_VER = ctypes.sizeof(NVDRS_SETTING) | (1 << 16)
NVDRS_PROFILE_VER = ctypes.sizeof(NVDRS_PROFILE) | (1 << 16)


class LUID(ctypes.Structure):
    _fields_ = [
        ("LowPart", wintypes.DWORD),
        ("HighPart", wintypes.LONG),
    ]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [
        ("Numerator", ctypes.c_uint32),
        ("Denominator", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_2DREGION(ctypes.Structure):
    _fields_ = [
        ("cx", ctypes.c_uint32),
        ("cy", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(ctypes.Structure):
    _fields_ = [
        ("pixelRate", ctypes.c_uint64),
        ("hSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("vSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("activeSize", DISPLAYCONFIG_2DREGION),
        ("totalSize", DISPLAYCONFIG_2DREGION),
        ("videoStandard", ctypes.c_uint32),
        ("scanLineOrdering", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_TARGET_MODE(ctypes.Structure):
    _fields_ = [("targetVideoSignalInfo", DISPLAYCONFIG_VIDEO_SIGNAL_INFO)]


class POINTL(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class DISPLAYCONFIG_SOURCE_MODE(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("pixelFormat", ctypes.c_uint32),
        ("position", POINTL),
    ]


class DISPLAYCONFIG_DESKTOP_IMAGE_INFO(ctypes.Structure):
    _fields_ = [
        ("pathSourceSize", DISPLAYCONFIG_2DREGION),
        ("desktopImageRegion", wintypes.RECT),
        ("desktopImageClip", wintypes.RECT),
    ]


class DISPLAYCONFIG_MODE_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("targetMode", DISPLAYCONFIG_TARGET_MODE),
        ("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
        ("desktopImageInfo", DISPLAYCONFIG_DESKTOP_IMAGE_INFO),
    ]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("infoType", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("adapterId", LUID),
        ("u", DISPLAYCONFIG_MODE_INFO_UNION),
    ]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
        ("modeInfoIdx", ctypes.c_uint32),
        ("statusFlags", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
        ("modeInfoIdx", ctypes.c_uint32),
        ("outputTechnology", ctypes.c_uint32),
        ("rotation", ctypes.c_uint32),
        ("scaling", ctypes.c_uint32),
        ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", ctypes.c_uint32),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", ctypes.c_wchar * CCHDEVICENAME),
    ]


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", ctypes.c_uint32),
        ("colorEncoding", ctypes.c_uint32),
        ("bitsPerColorChannel", ctypes.c_uint32),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * CCHDEVICENAME),
    ]


class NvApiUnavailable(RuntimeError):
    pass


def is_gpu_post_processing_enabled():
    try:
        enabled_features = get_enabled_gpu_driver_post_processing()
        enabled = bool(enabled_features)
        if enabled:
            logger.warning(f"GPU driver post-processing enabled: {enabled_features}")
        else:
            logger.info("GPU driver post-processing enabled: False")
        return enabled
    except Exception as e:
        logger.error("GPU driver post-processing check failed", e)
        return False


def get_enabled_gpu_driver_post_processing(target_exe_path: Optional[str] = None, target_hwnd: Optional[int] = None):
    """
    Return enabled driver-level post-processing features known to alter captured pixels.
    """
    if os.name != "nt":
        logger.info("GPU driver post-processing check skipped: not Windows")
        return []

    enabled: List[GpuDriverPostProcessing] = []

    windows_hdr_result = _run_gpu_feature_detector(
        "is_windows_hdr_enabled",
        lambda: is_windows_hdr_enabled(target_hwnd),
    )
    windows_hdr_active = bool(windows_hdr_result and windows_hdr_result.enabled)
    nvidia_filter_profile_active, nvidia_filter_profile_detail = _nvidia_filter_profile_in_use_state(target_exe_path)
    _log_nvidia_filter_profile_state(nvidia_filter_profile_active, nvidia_filter_profile_detail)
    if nvidia_filter_profile_active is True:
        enabled.append(
            GpuDriverPostProcessing(
                vendor="NVIDIA",
                feature="Filter Profile",
                enabled=True,
                detail=nvidia_filter_profile_detail,
            )
        )

    for detector_name, detector in (
        ("is_nvidia_image_sharpening_enabled", is_nvidia_image_sharpening_enabled),
        ("is_amd_image_sharpening_enabled", is_amd_image_sharpening_enabled),
    ):
        result = _run_gpu_feature_detector(detector_name, detector)
        if result and result.enabled:
            enabled.append(result)

    if nvidia_filter_profile_active is not False:
        result = _run_gpu_feature_detector(
            "is_nvidia_rtx_dynamic_vibrance_enabled",
            is_nvidia_rtx_dynamic_vibrance_enabled,
        )
        if result and result.enabled:
            enabled.append(result)
    else:
        logger.info(
            "NVIDIA RTX Dynamic Vibrance enabled: False "
            f"(NVIDIA filter profile is not in use: {nvidia_filter_profile_detail})"
        )

    if not windows_hdr_active:
        logger.info("NVIDIA RTX HDR enabled: False (Windows HDR is not enabled)")
    elif nvidia_filter_profile_active is not False:
        result = _run_gpu_feature_detector(
            "is_nvidia_rtx_hdr_enabled",
            lambda: is_nvidia_rtx_hdr_enabled(target_exe_path),
        )
        if result and result.enabled:
            enabled.append(result)
    else:
        logger.info(
            "NVIDIA RTX HDR enabled: False "
            f"(NVIDIA filter profile is not in use: {nvidia_filter_profile_detail})"
        )

    logger.info(f"GPU driver post-processing detected features: {enabled}")
    return enabled


def _run_gpu_feature_detector(detector_name: str, detector: Callable[[], Optional[GpuDriverPostProcessing]]):
    try:
        return detector()
    except Exception as e:
        logger.debug(f"{detector_name} skipped: {e}")
        return None


def is_windows_hdr_enabled(target_hwnd: Optional[int] = None) -> Optional[GpuDriverPostProcessing]:
    enabled, detail = _windows_hdr_enabled_state(target_hwnd)
    logger.info(f"Windows HDR enabled: {enabled} ({detail})")
    if not enabled:
        return None
    return GpuDriverPostProcessing(
        vendor="Windows",
        feature="HDR",
        enabled=True,
        detail=detail,
    )


def _log_nvidia_filter_profile_state(profile_in_use: Optional[bool], detail: str):
    state = "Unknown" if profile_in_use is None else str(profile_in_use)
    logger.info(f"NVIDIA filter profile in use: {state} ({detail})")


def is_nvidia_image_sharpening_enabled() -> Optional[GpuDriverPostProcessing]:
    result = _detect_nvidia_drs_flags(
        NV_DRS_IMAGE_SHARPENING_IDS,
        lambda value: value == 1,
        "Image Sharpening",
    )
    _log_feature_enabled("NVIDIA Image Sharpening", result)
    return result


def is_nvidia_rtx_dynamic_vibrance_enabled() -> Optional[GpuDriverPostProcessing]:
    result = _detect_nvidia_drs_flags(
        (NV_DRS_RTX_DYNAMIC_VIBRANCE_ENABLE_ID,),
        lambda value: value == 1,
        "RTX Dynamic Vibrance",
    )
    _log_feature_enabled("NVIDIA RTX Dynamic Vibrance", result)
    return result


def is_nvidia_rtx_hdr_enabled(target_exe_path: Optional[str] = None) -> Optional[GpuDriverPostProcessing]:
    hit = _detect_nvidia_drs_flags(
        (NV_DRS_RTX_HDR_ENABLE_ID,),
        lambda value: value == 1,
        "RTX HDR",
    )
    if hit:
        _log_feature_enabled("NVIDIA RTX HDR", hit)
        return hit

    result = _detect_nvidia_drs_flags(
        (NV_DRS_RTX_HDR_DRIVER_FLAGS_ID,),
        lambda value: value != 0,
        "RTX HDR",
        detail_suffix="driver_flags",
    )
    _log_feature_enabled("NVIDIA RTX HDR", result)
    return result


def _log_feature_enabled(feature_name: str, result: Optional[GpuDriverPostProcessing]):
    detail = f" ({result.detail})" if result and result.detail else ""
    logger.info(f"{feature_name} enabled: {bool(result and result.enabled)}{detail}")


def is_amd_image_sharpening_enabled() -> Optional[GpuDriverPostProcessing]:
    if importlib.util.find_spec("ADLXPybind") is None:
        logger.info("AMD image sharpening check skipped: ADLXPybind is not installed")
        return None

    ADLX = importlib.import_module("ADLXPybind")
    helper = ADLX.ADLXHelper()
    ret = helper.Initialize()
    try:
        adlx_ok = getattr(getattr(ADLX, "ADLX_RESULT", None), "ADLX_OK", 0)
        if ret != adlx_ok:
            logger.info(f"AMD image sharpening check skipped: ADLX initialize returned {ret}")
            return None

        system = helper.GetSystemServices()
        if system is None:
            logger.info("AMD image sharpening check skipped: ADLX system services unavailable")
            return None

        settings3d = _call_first_existing(system, ("Get3DSettingsServices", "Get3DSettingsService"))
        if settings3d is None:
            logger.info("AMD image sharpening check skipped: ADLXPybind has no 3D settings services API")
            return None

        gpu = _get_first_adlx_gpu(ADLX, system)
        sharpening = _get_adlx_image_sharpening(settings3d, gpu)
        if sharpening is None:
            logger.info("AMD image sharpening check skipped: ADLXPybind has no image sharpening API")
            return None

        supported = _call_first_existing(sharpening, ("IsSupported", "isSupported"))
        if supported is not None and not _adlx_bool(supported):
            logger.info("AMD image sharpening check skipped: image sharpening is not supported")
            return None

        enabled = _call_first_existing(sharpening, ("IsEnabled", "isEnabled", "GetEnabled", "enabled"))
        if enabled is None:
            logger.info("AMD image sharpening check skipped: image sharpening enabled state unavailable")
            return None

        is_enabled = _adlx_bool(enabled)
        logger.info(f"AMD Radeon Image Sharpening enabled: {is_enabled}")
        return GpuDriverPostProcessing(
            vendor="AMD",
            feature="Radeon Image Sharpening",
            enabled=is_enabled,
        )
    finally:
        terminate = getattr(helper, "Terminate", None)
        if terminate:
            terminate()


def _windows_hdr_enabled_state(target_hwnd: Optional[int] = None) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "not Windows"

    try:
        target_device_name = _monitor_device_name_from_hwnd(target_hwnd)
        paths = _query_active_display_paths()
        states = []

        for path in paths:
            source_name = _displayconfig_source_name(path.sourceInfo)
            if target_device_name and source_name.lower() != target_device_name.lower():
                continue

            advanced_color = _displayconfig_advanced_color_info(path.targetInfo)
            if advanced_color is None:
                continue

            enabled = bool(advanced_color.value & 0x2)
            supported = bool(advanced_color.value & 0x1)
            label = source_name or f"target={path.targetInfo.id}"
            states.append(
                (
                    enabled,
                    f"{label}: enabled={enabled}, supported={supported}, "
                    f"bits={advanced_color.bitsPerColorChannel}"
                )
            )

        if not states:
            if target_device_name:
                return False, f"no active HDR display info for {target_device_name}"
            return False, "no active HDR display info"

        enabled_states = [detail for enabled, detail in states if enabled]
        if enabled_states:
            return True, "; ".join(enabled_states)
        return False, "; ".join(detail for _enabled, detail in states)
    except Exception as e:
        logger.debug(f"Windows HDR check failed: {e}")
        return False, f"check failed: {e}"


def _query_active_display_paths() -> List[DISPLAYCONFIG_PATH_INFO]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetDisplayConfigBufferSizes.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    user32.GetDisplayConfigBufferSizes.restype = ctypes.c_long
    user32.QueryDisplayConfig.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(DISPLAYCONFIG_PATH_INFO),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(DISPLAYCONFIG_MODE_INFO),
        ctypes.c_void_p,
    ]
    user32.QueryDisplayConfig.restype = ctypes.c_long

    for _attempt in range(3):
        path_count = ctypes.c_uint32(0)
        mode_count = ctypes.c_uint32(0)
        status = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(path_count),
            ctypes.byref(mode_count),
        )
        if status != ERROR_SUCCESS:
            raise OSError(status, "GetDisplayConfigBufferSizes failed")

        paths = (DISPLAYCONFIG_PATH_INFO * path_count.value)()
        modes = (DISPLAYCONFIG_MODE_INFO * mode_count.value)()
        status = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(path_count),
            paths,
            ctypes.byref(mode_count),
            modes,
            None,
        )
        if status == ERROR_INSUFFICIENT_BUFFER:
            continue
        if status != ERROR_SUCCESS:
            raise OSError(status, "QueryDisplayConfig failed")
        return [paths[index] for index in range(path_count.value)]

    raise OSError(ERROR_INSUFFICIENT_BUFFER, "QueryDisplayConfig buffer changed repeatedly")


def _monitor_device_name_from_hwnd(target_hwnd: Optional[int]) -> str:
    if not target_hwnd:
        return ""

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    monitor = user32.MonitorFromWindow(wintypes.HWND(target_hwnd), MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return ""

    monitor_info = MONITORINFOEXW()
    monitor_info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
        return ""
    return monitor_info.szDevice or ""


def _displayconfig_source_name(source_info: DISPLAYCONFIG_PATH_SOURCE_INFO) -> str:
    info = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME
    info.header.size = ctypes.sizeof(DISPLAYCONFIG_SOURCE_DEVICE_NAME)
    info.header.adapterId = source_info.adapterId
    info.header.id = source_info.id

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]
    user32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
    status = user32.DisplayConfigGetDeviceInfo(
        ctypes.cast(ctypes.byref(info), ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER))
    )
    if status != ERROR_SUCCESS:
        return ""
    return info.viewGdiDeviceName or ""


def _displayconfig_advanced_color_info(
    target_info: DISPLAYCONFIG_PATH_TARGET_INFO,
) -> Optional[DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO]:
    info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
    info.header.size = ctypes.sizeof(DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO)
    info.header.adapterId = target_info.adapterId
    info.header.id = target_info.id

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]
    user32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
    status = user32.DisplayConfigGetDeviceInfo(
        ctypes.cast(ctypes.byref(info), ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER))
    )
    if status != ERROR_SUCCESS:
        logger.debug(f"DisplayConfigGetDeviceInfo advanced color failed: {status}")
        return None
    return info


def _nvidia_filter_profile_in_use_state(target_exe_path: Optional[str]) -> Tuple[Optional[bool], str]:
    if os.name != "nt":
        return None, "not Windows"
    if not target_exe_path:
        return None, "target exe unavailable"

    paths = _fresh_nvidia_overlay_log_paths()
    if not paths:
        return None, "fresh NVIDIA Overlay log unavailable"

    last_slot: Optional[int] = None
    last_detail = ""
    for path in paths:
        text = _read_file_tail(path, NVIDIA_OVERLAY_LOG_TAIL_BYTES)
        if not text:
            continue
        slot, detail = _nvidia_filter_profile_slot_from_text(text, target_exe_path, os.path.basename(path))
        if slot is not None:
            last_slot = slot
            last_detail = detail

    if last_slot is None:
        target_detail = f" for {target_exe_path}" if target_exe_path else ""
        return None, f"NVIDIA filter profile slot not found{target_detail}"
    return last_slot > 0, last_detail


def _fresh_nvidia_overlay_log_paths() -> List[str]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []

    log_dir = os.path.join(local_app_data, "NVIDIA Corporation", "NVIDIA Overlay")
    candidates = [
        os.path.join(log_dir, "console.log.bak"),
        os.path.join(log_dir, "console.log"),
    ]
    now = time.time()
    paths = []
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            if now - os.path.getmtime(path) <= NVIDIA_FILTER_PROFILE_LOG_MAX_AGE_SECONDS:
                paths.append(path)
        except OSError:
            continue
    return paths


def _read_file_tail(path: str, max_bytes: int) -> str:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace")
    except OSError as e:
        logger.debug(f"Failed to read NVIDIA Overlay log {path}: {e}")
        return ""


def _nvidia_filter_profile_slot_from_text(
    text: str,
    target_exe_path: Optional[str],
    source_name: str = "NVIDIA Overlay log",
) -> Tuple[Optional[int], str]:
    target = _normalize_windows_path(target_exe_path) if target_exe_path else ""
    last_target_line: Optional[int] = None
    last_slot: Optional[int] = None
    last_detail = ""

    for line_number, line in enumerate(text.splitlines(), 1):
        normalized_line = _normalize_windows_path(line)
        has_target = bool(target and target in normalized_line)
        if has_target:
            last_target_line = line_number

        slot = _nvidia_filter_profile_slot_from_line(line)
        if slot is None:
            continue

        lower_line = line.lower()
        line_has_context = (
            "gamefilter" in lower_line
            or "applyslot" in lower_line
            or "filtersslotchanged" in lower_line
            or "processingfilter" in lower_line
        )
        near_target = (
            not target
            or has_target
            or (
                last_target_line is not None
                and line_number - last_target_line <= NVIDIA_OVERLAY_TARGET_CONTEXT_LINES
            )
        )
        if line_has_context and near_target:
            last_slot = slot
            last_detail = f"slot={slot}, source={source_name}:{line_number}"

    return last_slot, last_detail


def _nvidia_filter_profile_slot_from_line(line: str) -> Optional[int]:
    telemetry_match = re.search(r'"newSlotID"\s*:\s*(\d+)', line)
    if telemetry_match:
        return int(telemetry_match.group(1))

    active_slot_match = re.search(r"current active slot\s*=\s*(\d+)", line, re.IGNORECASE)
    if active_slot_match:
        return int(active_slot_match.group(1))

    apply_slot_match = re.search(r"applyslot index:\s*(\d+)", line, re.IGNORECASE)
    if apply_slot_match:
        return int(apply_slot_match.group(1))

    return None


def _normalize_windows_path(value: Optional[str]) -> str:
    return (value or "").replace("\\", "/").lower()


def _detect_nvidia_drs_flags(
    setting_ids: Iterable[int],
    is_enabled_value: Callable[[int], bool],
    feature_name: str,
    detail_suffix: str = "value",
) -> Optional[GpuDriverPostProcessing]:
    api_hits = _scan_nvapi_profiles(setting_ids, is_enabled_value)
    if api_hits:
        profile_name, setting_id, value, setting_label = api_hits[0]
        detail = f"{detail_suffix}={value}"
        if setting_label:
            detail = f"{setting_label}, {detail}"
        if profile_name:
            detail = f"{profile_name}: {detail}"
        return GpuDriverPostProcessing(
            vendor="NVIDIA",
            feature=feature_name,
            enabled=True,
            detail=detail,
        )

    for setting_id in setting_ids:
        if _nv_drs_db_setting_is_on(setting_id, is_enabled_value):
            values = _read_nv_drs_db_values(setting_id)
            return GpuDriverPostProcessing(
                vendor="NVIDIA",
                feature=feature_name,
                enabled=True,
                detail=f"nvdrsdb {detail_suffix}={values} (id=0x{setting_id:08X})",
            )

    return None


def _scan_nvapi_profiles(
    setting_ids: Iterable[int],
    is_enabled_value: Callable[[int], bool],
) -> List[Tuple[str, int, int, str]]:
    hits: List[Tuple[str, int, int, str]] = []
    try:
        with _nvapi_drs_session() as (nvapi, session):
            profile_handles = _list_profile_handles(nvapi, session)
            for profile_name, profile_handle in profile_handles:
                for setting_id in setting_ids:
                    status, value, setting_label = _nvapi_get_setting_u32(
                        nvapi, session, profile_handle, setting_id
                    )
                    if status == NVAPI_OK and is_enabled_value(value):
                        hits.append((profile_name, setting_id, value, setting_label))
    except NvApiUnavailable as e:
        _log_nvapi_profile_scan_skipped(e)
    return hits


def _list_profile_handles(nvapi, session) -> List[Tuple[str, ctypes.c_void_p]]:
    handles: List[Tuple[str, ctypes.c_void_p]] = []
    seen = set()

    def add(name: str, handle: ctypes.c_void_p):
        key = handle.value or 0
        if key and key not in seen:
            seen.add(key)
            handles.append((name, handle))

    for profile_name in ("Base Profile",):
        handle = ctypes.c_void_p()
        status = nvapi.drs_find_profile_by_name(session, profile_name, ctypes.byref(handle))
        if status == NVAPI_OK:
            add(profile_name, handle)

    global_handle = ctypes.c_void_p()
    status = nvapi.drs_get_current_global_profile(session, ctypes.byref(global_handle))
    if status == NVAPI_OK:
        add("Global Profile", global_handle)

    return handles


def _nvapi_profile_name(nvapi, session, profile_handle) -> str:
    profile = NVDRS_PROFILE()
    profile.version = NVDRS_PROFILE_VER
    status = nvapi.drs_get_profile_info(session, profile_handle, ctypes.byref(profile))
    if status != NVAPI_OK:
        return ""
    return profile.profileName or ""


def _nvapi_get_setting_u32(nvapi, session, profile_handle, setting_id: int):
    setting = NVDRS_SETTING()
    setting.version = NVDRS_SETTING_VER
    internal = ctypes.c_uint32(0)
    status = nvapi.drs_get_setting(
        session,
        profile_handle,
        setting_id,
        ctypes.byref(setting),
        ctypes.byref(internal),
    )
    if status != NVAPI_OK:
        return status, 0, ""
    value = int.from_bytes(bytes(setting.currentValue.rawData[:4]), "little")
    label = setting.settingName or ""
    return status, value, label


def _read_nv_drs_db_values(setting_id: int) -> List[int]:
    values: List[int] = []
    needle = struct.pack("<I", setting_id)
    for path in NV_DRS_DB_PATHS:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        start = 0
        while True:
            offset = data.find(needle, start)
            if offset < 0:
                break
            if offset + 12 <= len(data):
                setting_type = struct.unpack_from("<I", data, offset + 4)[0]
                value = struct.unpack_from("<I", data, offset + 8)[0]
                if setting_type == 0x1002:
                    values.append(value)
            start = offset + 1
    return values


def _nv_drs_db_setting_is_on(setting_id: int, is_enabled_value: Callable[[int], bool]) -> bool:
    """
    nvdrsdb is a fallback when NvAPI returns NOT_FOUND on this driver stack.
    Require every matched record to satisfy is_enabled_value to avoid stale [1, 0] hits.
    """
    values = _read_nv_drs_db_values(setting_id)
    if not values:
        return False
    return all(is_enabled_value(value) for value in values)


@contextmanager
def _nvapi_drs_session():
    global _NVAPI_INIT_UNAVAILABLE_MESSAGE

    if _NVAPI_INIT_UNAVAILABLE_MESSAGE is not None:
        raise NvApiUnavailable(_NVAPI_INIT_UNAVAILABLE_MESSAGE)

    try:
        nvapi = _NvApi()
    except NvApiUnavailable as e:
        _NVAPI_INIT_UNAVAILABLE_MESSAGE = str(e)
        raise

    session = ctypes.c_void_p()
    status = nvapi.drs_create_session(ctypes.byref(session))
    if status != NVAPI_OK:
        raise NvApiUnavailable(f"NvAPI_DRS_CreateSession failed: {status}")
    try:
        status = nvapi.drs_load_settings(session)
        if status != NVAPI_OK:
            raise NvApiUnavailable(f"NvAPI_DRS_LoadSettings failed: {status}")
        yield nvapi, session
    finally:
        nvapi.drs_destroy_session(session)


def _log_nvapi_profile_scan_skipped(error: NvApiUnavailable):
    global _NVAPI_INIT_UNAVAILABLE_LOGGED

    if str(error) == _NVAPI_INIT_UNAVAILABLE_MESSAGE:
        if _NVAPI_INIT_UNAVAILABLE_LOGGED:
            return
        _NVAPI_INIT_UNAVAILABLE_LOGGED = True
    logger.debug(f"NvAPI profile scan skipped: {error}")


def _get_first_adlx_gpu(ADLX, system):
    gpu_holder_cls = getattr(ADLX, "ADLXGPUHolder", None)
    if gpu_holder_cls:
        gpu_holder = gpu_holder_cls()
        gpu = _call_first_existing(gpu_holder, ("getGPU", "GetGPU"))
        if gpu is not None:
            return gpu

    gpu_list = _call_first_existing(system, ("GetGPUs", "GetGPUList", "getGPUList"))
    if gpu_list is None:
        return None
    if isinstance(gpu_list, (list, tuple)):
        return gpu_list[0] if gpu_list else None
    for method_name in ("At", "at", "Get", "get"):
        method = getattr(gpu_list, method_name, None)
        if method:
            try:
                return method(0)
            except Exception:
                pass
    return None


def _get_adlx_image_sharpening(settings3d, gpu):
    method_names = (
        "GetImageSharpening",
        "GetImageSharpenDesktop",
        "Get3DImageSharpening",
        "GetRadeonImageSharpening",
    )
    for method_name in method_names:
        method = getattr(settings3d, method_name, None)
        if method is None:
            continue
        for args in ((gpu,), ()):
            if args and args[0] is None:
                continue
            try:
                result = method(*args)
                if result is not None:
                    return result
            except TypeError:
                continue
    return None


def _call_first_existing(obj, method_names):
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if method is None:
            continue
        try:
            return method()
        except TypeError:
            continue
    return None


def _adlx_bool(value):
    if isinstance(value, (list, tuple)):
        if not value:
            return False
        value = value[-1]
    return bool(value)


class _NvApi:
    def __init__(self):
        self.dll = self._load_nvapi()
        query_interface = getattr(self.dll, "nvapi_QueryInterface", None)
        if query_interface is None:
            query_interface = getattr(self.dll, "NvAPI_QueryInterface", None)
        if query_interface is None:
            raise NvApiUnavailable("NvAPI_QueryInterface not found")

        query_interface.argtypes = [ctypes.c_uint32]
        query_interface.restype = ctypes.c_void_p
        self._query_interface = query_interface

        self.initialize = self._get_function(0x0150E828, ctypes.c_int)
        self.drs_create_session = self._get_function(
            0x0694D52E,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        )
        self.drs_destroy_session = self._get_function(
            0xDAD9CFF8,
            ctypes.c_int,
            ctypes.c_void_p,
        )
        self.drs_load_settings = self._get_function(
            0x375DBD6B,
            ctypes.c_int,
            ctypes.c_void_p,
        )
        self.drs_get_setting = self._get_function(
            0x73BF8338,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(NVDRS_SETTING),
            ctypes.POINTER(ctypes.c_uint32),
        )
        self.drs_get_current_global_profile = self._get_function(
            NVAPI_DRS_GET_CURRENT_GLOBAL_PROFILE,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        self.drs_find_profile_by_name = self._get_function(
            NVAPI_DRS_FIND_PROFILE_BY_NAME,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        self.drs_enum_profiles = self._get_function(
            NVAPI_DRS_ENUM_PROFILES,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        )
        self.drs_get_profile_info = self._get_function(
            NVAPI_DRS_GET_PROFILE_INFO,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(NVDRS_PROFILE),
        )
        status = self.initialize()
        if status == NVAPI_NVIDIA_DEVICE_NOT_FOUND:
            raise NvApiUnavailable("No NVIDIA device found")
        if status != NVAPI_OK:
            raise NvApiUnavailable(f"NvAPI_Initialize failed: {status}")

    @staticmethod
    def _load_nvapi():
        try:
            return ctypes.CDLL("nvapi64.dll")
        except OSError:
            return ctypes.CDLL("nvapi.dll")

    def _get_function(self, function_id, restype, *argtypes):
        address = self._query_interface(function_id)
        if not address:
            raise NvApiUnavailable(f"NvAPI function 0x{function_id:08X} not found")
        return ctypes.CFUNCTYPE(restype, *argtypes)(address)


def main():
    enabled_features = get_enabled_gpu_driver_post_processing()
    enabled = bool(enabled_features)
    logger.info(f"is_gpu_post_processing_enabled={enabled}")
    for feature in enabled_features:
        detail = f" ({feature.detail})" if feature.detail else ""
        logger.info(f"{feature.vendor}: {feature.feature}{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
