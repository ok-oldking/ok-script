import ctypes
import importlib
import importlib.util
import os
import struct
from contextlib import contextmanager
from dataclasses import dataclass
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


def get_enabled_gpu_driver_post_processing():
    """
    Return enabled driver-level post-processing features known to alter captured pixels.
    """
    if os.name != "nt":
        logger.info("GPU driver post-processing check skipped: not Windows")
        return []

    enabled: List[GpuDriverPostProcessing] = []
    for detector in (
        is_nvidia_image_sharpening_enabled,
        is_nvidia_rtx_dynamic_vibrance_enabled,
        is_nvidia_rtx_hdr_enabled,
        is_amd_image_sharpening_enabled,
    ):
        try:
            result = detector()
            if result and result.enabled:
                enabled.append(result)
        except Exception as e:
            logger.debug(f"{detector.__name__} skipped: {e}")

    logger.info(f"GPU driver post-processing detected features: {enabled}")
    return enabled


def is_nvidia_image_sharpening_enabled() -> Optional[GpuDriverPostProcessing]:
    return _detect_nvidia_drs_flags(
        NV_DRS_IMAGE_SHARPENING_IDS,
        lambda value: value == 1,
        "NVIDIA Image Sharpening",
    )


def is_nvidia_rtx_dynamic_vibrance_enabled() -> Optional[GpuDriverPostProcessing]:
    return _detect_nvidia_drs_flags(
        (NV_DRS_RTX_DYNAMIC_VIBRANCE_ENABLE_ID,),
        lambda value: value == 1,
        "RTX Dynamic Vibrance",
    )


def is_nvidia_rtx_hdr_enabled() -> Optional[GpuDriverPostProcessing]:
    hit = _detect_nvidia_drs_flags(
        (NV_DRS_RTX_HDR_ENABLE_ID,),
        lambda value: value == 1,
        "RTX HDR",
    )
    if hit:
        return hit

    return _detect_nvidia_drs_flags(
        (NV_DRS_RTX_HDR_DRIVER_FLAGS_ID,),
        lambda value: value != 0,
        "RTX HDR",
        detail_suffix="driver_flags",
    )


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

        return GpuDriverPostProcessing(
            vendor="AMD",
            feature="AMD Radeon Image Sharpening",
            enabled=_adlx_bool(enabled),
        )
    finally:
        terminate = getattr(helper, "Terminate", None)
        if terminate:
            terminate()


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
