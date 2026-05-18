import ctypes
import importlib
import importlib.util
import os
from dataclasses import dataclass
from typing import Optional

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


NVAPI_OK = 0
NVAPI_SETTING_NOT_FOUND = -163
NVAPI_NVIDIA_DEVICE_NOT_FOUND = -6
NV_QUALITY_UPSCALING_ID = 0x10444444
NV_QUALITY_UPSCALING_ON = 1
NVAPI_UNICODE_STRING_MAX = 2048
NVAPI_BINARY_DATA_MAX = 4096


@dataclass(frozen=True)
class GpuDriverPostProcessing:
    vendor: str
    feature: str
    enabled: bool
    detail: Optional[str] = None


class NVDRS_BINARY_SETTING(ctypes.Structure):
    _fields_ = [
        ("valueLength", ctypes.c_uint32),
        ("valueData", ctypes.c_ubyte * NVAPI_BINARY_DATA_MAX),
    ]


class NVDRS_SETTING_VALUE(ctypes.Union):
    _fields_ = [
        ("u32Value", ctypes.c_uint32),
        ("binaryValue", NVDRS_BINARY_SETTING),
        ("wszValue", ctypes.c_wchar * NVAPI_UNICODE_STRING_MAX),
    ]


class NVDRS_SETTING(ctypes.Structure):
    _anonymous_ = ("predefinedValue", "currentValue")
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("settingName", ctypes.c_wchar * NVAPI_UNICODE_STRING_MAX),
        ("settingId", ctypes.c_uint32),
        ("settingType", ctypes.c_int),
        ("settingLocation", ctypes.c_int),
        ("isCurrentPredefined", ctypes.c_uint32),
        ("isPredefinedValid", ctypes.c_uint32),
        ("predefinedValue", NVDRS_SETTING_VALUE),
        ("currentValue", NVDRS_SETTING_VALUE),
    ]


NVDRS_SETTING_VER = ctypes.sizeof(NVDRS_SETTING) | (1 << 16)


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

    enabled = []
    try:
        nvidia_quality_upscaling = is_nvidia_quality_upscaling_enabled()
        if nvidia_quality_upscaling and nvidia_quality_upscaling.enabled:
            enabled.append(nvidia_quality_upscaling)
    except Exception as e:
        logger.debug(f"NVIDIA driver post-processing check skipped: {e}")
    try:
        amd_image_sharpening = is_amd_image_sharpening_enabled()
        if amd_image_sharpening and amd_image_sharpening.enabled:
            enabled.append(amd_image_sharpening)
    except Exception as e:
        logger.debug(f"AMD driver post-processing check skipped: {e}")
    logger.info(f"GPU driver post-processing detected features: {enabled}")
    return enabled


def is_nvidia_quality_upscaling_enabled():
    nvapi = _NvApi()
    session = ctypes.c_void_p()
    status = nvapi.drs_create_session(ctypes.byref(session))
    if status != NVAPI_OK:
        raise NvApiUnavailable(f"NvAPI_DRS_CreateSession failed: {status}")

    try:
        status = nvapi.drs_load_settings(session)
        if status != NVAPI_OK:
            raise NvApiUnavailable(f"NvAPI_DRS_LoadSettings failed: {status}")

        setting = NVDRS_SETTING()
        setting.version = NVDRS_SETTING_VER
        status = nvapi.drs_get_setting(
            session,
            _global_profile_handle(),
            NV_QUALITY_UPSCALING_ID,
            ctypes.byref(setting),
        )
        if status == NVAPI_SETTING_NOT_FOUND:
            return None
        if status != NVAPI_OK:
            raise NvApiUnavailable(f"NvAPI_DRS_GetSetting failed: {status}")

        enabled = setting.u32Value == NV_QUALITY_UPSCALING_ON
        return GpuDriverPostProcessing(
            vendor="NVIDIA",
            feature="NVIDIA Image Scaling / Quality Upscaling",
            enabled=enabled,
        )
    finally:
        nvapi.drs_destroy_session(session)


def is_amd_image_sharpening_enabled():
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
        function = ctypes.CFUNCTYPE(restype, *argtypes)(address)
        return function


def _global_profile_handle():
    pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
    return ctypes.c_void_p((1 << pointer_bits) - 1)


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
