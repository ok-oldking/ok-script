import unittest
from unittest.mock import patch

from ok.util import gpu_driver_settings as gpu_settings
from ok.util.gpu_driver_settings import GpuDriverPostProcessing


class TestGpuDriverSettings(unittest.TestCase):
    def test_rtx_hdr_reports_drs_hit_without_precondition_checks(self):
        drs_hit = GpuDriverPostProcessing("NVIDIA", "RTX HDR", True, "Global Profile: value=1")

        with patch.object(gpu_settings, "_detect_nvidia_drs_flags", return_value=drs_hit), \
                patch.object(gpu_settings, "_windows_hdr_enabled_state") as hdr_state:
            result = gpu_settings.is_nvidia_rtx_hdr_enabled(r"C:\Game\game.exe")

        self.assertEqual(drs_hit, result)
        hdr_state.assert_not_called()

    def test_unknown_nvidia_filter_profile_does_not_block_detected_features(self):
        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "is_windows_hdr_enabled", return_value=None), \
                patch.object(gpu_settings, "_nvidia_filter_profile_in_use_state",
                             return_value=(None, "profile unavailable")), \
                patch.object(gpu_settings, "is_nvidia_image_sharpening_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_dynamic_vibrance_enabled", return_value=None) as vibrance_enabled, \
                patch.object(gpu_settings, "is_nvidia_rtx_hdr_enabled") as rtx_hdr_enabled, \
                patch.object(gpu_settings, "is_amd_image_sharpening_enabled", return_value=None):
            fake_os.name = "nt"
            result = gpu_settings.get_enabled_gpu_driver_post_processing(r"C:\Game\game.exe", 100)

        self.assertEqual([], result)
        vibrance_enabled.assert_called_once_with()
        rtx_hdr_enabled.assert_not_called()

    def test_get_enabled_reports_rtx_hdr_when_windows_hdr_is_on(self):
        rtx_hdr = GpuDriverPostProcessing("NVIDIA", "RTX HDR", True, "Global Profile: value=1")

        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "is_windows_hdr_enabled",
                             return_value=GpuDriverPostProcessing("Windows", "HDR", True)), \
                patch.object(gpu_settings, "_nvidia_filter_profile_in_use_state",
                             return_value=(None, "profile unavailable")), \
                patch.object(gpu_settings, "is_nvidia_image_sharpening_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_dynamic_vibrance_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_hdr_enabled", return_value=rtx_hdr), \
                patch.object(gpu_settings, "is_amd_image_sharpening_enabled", return_value=None):
            fake_os.name = "nt"
            result = gpu_settings.get_enabled_gpu_driver_post_processing(r"C:\Game\game.exe", 100)

        self.assertEqual([rtx_hdr], result)

    def test_get_enabled_reports_nvidia_filter_profile_when_in_use(self):
        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "is_windows_hdr_enabled", return_value=None), \
                patch.object(gpu_settings, "_nvidia_filter_profile_in_use_state",
                             return_value=(True, "slot=1")), \
                patch.object(gpu_settings, "is_nvidia_image_sharpening_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_dynamic_vibrance_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_hdr_enabled") as rtx_hdr_enabled, \
                patch.object(gpu_settings, "is_amd_image_sharpening_enabled", return_value=None):
            fake_os.name = "nt"
            result = gpu_settings.get_enabled_gpu_driver_post_processing(r"C:\Game\game.exe", 100)

        self.assertEqual(
            [GpuDriverPostProcessing("NVIDIA", "Filter Profile", True, "slot=1")],
            result,
        )
        rtx_hdr_enabled.assert_not_called()

    def test_get_enabled_skips_rtx_hdr_when_windows_hdr_is_off(self):
        dynamic_vibrance = GpuDriverPostProcessing("NVIDIA", "RTX Dynamic Vibrance", True)

        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "is_windows_hdr_enabled", return_value=None), \
                patch.object(gpu_settings, "_nvidia_filter_profile_in_use_state",
                             return_value=(None, "profile unavailable")), \
                patch.object(gpu_settings, "is_nvidia_image_sharpening_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_dynamic_vibrance_enabled",
                             return_value=dynamic_vibrance), \
                patch.object(gpu_settings, "is_nvidia_rtx_hdr_enabled") as rtx_hdr_enabled, \
                patch.object(gpu_settings, "is_amd_image_sharpening_enabled", return_value=None):
            fake_os.name = "nt"
            result = gpu_settings.get_enabled_gpu_driver_post_processing(r"C:\Game\game.exe", 100)

        self.assertEqual([dynamic_vibrance], result)
        rtx_hdr_enabled.assert_not_called()

    def test_get_enabled_skips_rtx_filters_when_filter_profile_is_known_inactive(self):
        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "is_windows_hdr_enabled",
                             return_value=GpuDriverPostProcessing("Windows", "HDR", True)), \
                patch.object(gpu_settings, "_nvidia_filter_profile_in_use_state",
                             return_value=(False, "slot=0")), \
                patch.object(gpu_settings, "is_nvidia_image_sharpening_enabled", return_value=None), \
                patch.object(gpu_settings, "is_nvidia_rtx_dynamic_vibrance_enabled") as vibrance_enabled, \
                patch.object(gpu_settings, "is_nvidia_rtx_hdr_enabled") as rtx_hdr_enabled, \
                patch.object(gpu_settings, "is_amd_image_sharpening_enabled", return_value=None):
            fake_os.name = "nt"
            result = gpu_settings.get_enabled_gpu_driver_post_processing(r"C:\Game\game.exe", 100)

        self.assertEqual([], result)
        vibrance_enabled.assert_not_called()
        rtx_hdr_enabled.assert_not_called()

    def test_nvidia_filter_profile_slot_parser_uses_latest_target_slot(self):
        text = (
            'drsName":"g:/game/game.exe"\n'
            "GameFilter  current active slot =  1\n"
            '{"name":"ProcessingFilter","parameters":{"action":"FiltersSlotChanged",'
            '"newSlotID":0,"drsName":"g:/game/game.exe"}}\n'
        )

        slot, detail = gpu_settings._nvidia_filter_profile_slot_from_text(
            text,
            r"g:\game\game.exe",
            "console.log",
        )

        self.assertEqual(0, slot)
        self.assertIn("slot=0", detail)

    def test_nvidia_filter_profile_is_unknown_without_target_exe(self):
        with patch.object(gpu_settings, "os") as fake_os, \
                patch.object(gpu_settings, "_fresh_nvidia_overlay_log_paths") as log_paths:
            fake_os.name = "nt"
            result = gpu_settings._nvidia_filter_profile_in_use_state(None)

        self.assertEqual((None, "target exe unavailable"), result)
        log_paths.assert_not_called()


if __name__ == "__main__":
    unittest.main()
