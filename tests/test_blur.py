import unittest
import threading
import time

import numpy as np

from ok import og
from ok.feature.Box import Box
from ok.gui.debug.Screenshot import Screenshot
from ok.util.blur import (
    BLUR_ALGORITHM,
    DEFAULT_BLUR_ALGORITHM,
    INPAINT_ALGORITHM,
    BlurOverlayProcessor,
    apply_blur_areas,
    get_blur_rects,
    patches_changed,
)


class TestBlurAreas(unittest.TestCase):
    @staticmethod
    def wait_for(condition, timeout=1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(0.01)
        return condition()

    def test_get_blur_rects_accepts_single_box_and_clamps_to_frame(self):
        rects = get_blur_rects(lambda width, height: Box(-5, 8, 20, 30), 12, 20)

        self.assertEqual([(0, 8, 12, 12)], rects)

    def test_apply_blur_areas_only_modifies_selected_region(self):
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        for x in range(8):
            frame[5:13, 5 + x] = x * 30
        original = frame.copy()

        result = apply_blur_areas(frame, lambda width, height: Box(5, 5, 8, 8))

        self.assertTrue(np.array_equal(frame, original))
        self.assertTrue(np.array_equal(result[:5], original[:5]))
        self.assertFalse(np.array_equal(result[5:13, 5:13], original[5:13, 5:13]))

    def test_inpaint_algorithm_reconstructs_selected_region_from_surroundings(self):
        frame = np.full((30, 30, 3), 180, dtype=np.uint8)
        frame[10:20, 10:20] = 0
        original = frame.copy()

        result = apply_blur_areas(
            frame, lambda width, height: Box(10, 10, 10, 10), INPAINT_ALGORITHM)

        self.assertTrue(np.array_equal(frame, original))
        self.assertTrue(np.array_equal(result[:10], original[:10]))
        self.assertGreater(float(result[10:20, 10:20].mean()), 100)

    def test_patch_change_detection_ignores_small_pixel_noise(self):
        patch = np.full((4, 4, 3), 100, dtype=np.uint8)
        small_change = np.full((4, 4, 3), 101, dtype=np.uint8)
        large_change = np.full((4, 4, 3), 180, dtype=np.uint8)

        self.assertFalse(patches_changed([(0, 0, 4, 4, patch)], [(0, 0, 4, 4, small_change)]))
        self.assertTrue(patches_changed([(0, 0, 4, 4, patch)], [(0, 0, 4, 4, large_change)]))

    def test_overlay_processor_only_emits_while_game_window_is_foreground(self):
        stopped = threading.Event()
        emitted = threading.Event()
        cleared = threading.Event()
        calls = []
        processor = BlurOverlayProcessor(
            lambda width, height: Box(0, 0, width, height),
            lambda: True,
            lambda patches: (calls.append(threading.current_thread().name), emitted.set()),
            lambda: cleared.set(),
            stopped)
        try:
            processor.next_frame(np.full((8, 8, 3), 30, dtype=np.uint8))
            self.assertFalse(emitted.wait(timeout=0.05))
            processor.set_visible(True)
            processor.next_frame(np.full((8, 8, 3), 30, dtype=np.uint8))
            self.assertTrue(emitted.wait(timeout=1))
            self.assertEqual(['BlurOverlay'], calls)
            processor.set_visible(False)
            self.assertTrue(cleared.wait(timeout=1))
        finally:
            stopped.set()

    def test_overlay_processor_uses_configured_interval_between_updates(self):
        stopped = threading.Event()
        emitted = []
        current_interval = [17]

        processor = BlurOverlayProcessor(
            lambda width, height: Box(0, 0, width, height),
            lambda: True,
            lambda patches: emitted.append(patches),
            lambda: None,
            stopped,
            interval=lambda: current_interval[0])
        try:
            processor.set_visible(True)
            first = np.full((8, 8, 3), 30, dtype=np.uint8)
            processor.next_frame(first)
            self.assertTrue(self.wait_for(lambda: len(emitted) == 1))
            processor.next_frame(np.full((8, 8, 3), 200, dtype=np.uint8))
            time.sleep(0.05)
            self.assertEqual(1, len(emitted))
            current_interval[0] = 0
            processor.next_frame(np.full((8, 8, 3), 200, dtype=np.uint8))
            self.assertTrue(self.wait_for(lambda: len(emitted) == 2))
        finally:
            stopped.set()

    def test_overlay_processor_applies_selected_algorithm(self):
        stopped = threading.Event()
        emitted = threading.Event()
        patches = []
        frame = np.full((30, 30, 3), 180, dtype=np.uint8)
        frame[10:20, 10:20] = 0

        processor = BlurOverlayProcessor(
            lambda width, height: Box(10, 10, 10, 10),
            lambda: True,
            lambda value: (patches.extend(value), emitted.set()),
            lambda: None,
            stopped,
            algorithm=lambda: INPAINT_ALGORITHM)
        try:
            processor.set_visible(True)
            processor.next_frame(frame)
            self.assertTrue(emitted.wait(timeout=1))
            self.assertGreater(float(patches[0][4].mean()), 100)
        finally:
            stopped.set()

    def test_screenshot_processor_receives_already_blurred_frame(self):
        original_config = og.config
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        frame[4:12, 4:12, 0] = np.arange(8) * 30
        received = []

        def processor(processed_frame):
            received.append(processed_frame.copy())
            return processed_frame

        try:
            blur_area = lambda width, height: Box(4, 4, 8, 8)
            og.config = {'blur_area': blur_area, 'screenshot_processor': processor}

            Screenshot.to_pil_image(None, frame)

            self.assertEqual(INPAINT_ALGORITHM, DEFAULT_BLUR_ALGORITHM)
            self.assertTrue(np.array_equal(received[0], apply_blur_areas(frame, blur_area, INPAINT_ALGORITHM)))
        finally:
            og.config = original_config

    def test_screenshot_uses_selected_global_algorithm(self):
        original_config = og.config
        original_global_config = getattr(og, 'global_config', None)
        frame = np.full((30, 30, 3), 180, dtype=np.uint8)
        frame[10:20, 10:20] = 0
        received = []

        class GlobalConfig:
            @staticmethod
            def get_config(name):
                return {'Blur Algorithm': INPAINT_ALGORITHM}

        try:
            blur_area = lambda width, height: Box(10, 10, 10, 10)
            og.config = {'blur_area': blur_area,
                         'screenshot_processor': lambda image: received.append(image.copy()) or image}
            og.global_config = GlobalConfig()

            Screenshot.to_pil_image(None, frame)

            self.assertGreater(float(received[0][10:20, 10:20].mean()), 100)
        finally:
            og.config = original_config
            og.global_config = original_global_config

    def test_explicit_screenshot_processor_runs_after_blur_without_using_config_processor(self):
        original_config = og.config
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        frame[4:12, 4:12, 0] = np.arange(8) * 30
        configured_calls = []
        explicit_frames = []

        def explicit_processor(processed_frame):
            explicit_frames.append(processed_frame.copy())
            return processed_frame

        try:
            blur_area = lambda width, height: Box(4, 4, 8, 8)
            og.config = {'blur_area': blur_area,
                         'screenshot_processor': lambda image: configured_calls.append(image)}

            Screenshot.to_pil_image(None, frame, processor=explicit_processor)

            self.assertEqual([], configured_calls)
            self.assertTrue(np.array_equal(explicit_frames[0],
                                           apply_blur_areas(frame, blur_area, INPAINT_ALGORITHM)))
        finally:
            og.config = original_config
