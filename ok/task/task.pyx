## Task.pyx
import re
import subprocess
import threading
import time
from typing import List

import cv2
from qfluentwidgets import FluentIcon

from ok.feature.Box import find_boxes_by_name, find_boxes_within_boundary, Box, find_box_by_name, relative_box, \
    sort_boxes, find_highest_confidence_box
from ok.feature.FeatureSet import adjust_coordinates
from ok.gui.Communicate import communicate
from ok.util.color import calculate_color_percentage
from ok.util.config import Config
from ok.util.handler import Handler
from ok.util.logger import Logger
from ok.util.process import create_shortcut

logger = Logger.get_logger(__name__)

cdef class ExecutorOperation:
    cdef double last_click_time
    cdef public object _executor
    cdef public object logger, _app

    def __init__(self, executor, app):
        self._executor = executor
        self._app = app
        self.logger = Logger.get_logger(self.__class__.__name__)
        self.last_click_time = 0

    def exit_is_set(self):
        return self.executor.exit_event.is_set()

    def get_task_by_class(self, cls):
        return self.executor.get_task_by_class(cls)

    def box_in_horizontal_center(self, box, off_percent=0.02):
        if box is None:
            return False

        center = self.executor.method.width / 2
        box_center = box.x + box.width / 2

        offset = abs(box_center - center)

        if offset / self.executor.method.width < off_percent:
            return True
        else:
            return False

    @property
    def executor(self):
        return self._executor

    @property
    def debug(self):
        return self.executor.debug

    def start_device(self):
        self._app.start_controller.start_device()

    def clipboard(self):
        from ok.third_party.paperclip import paste
        return paste()

    def is_scene(self, the_scene):
        return isinstance(self.executor.current_scene, the_scene)

    def reset_scene(self):
        self.executor.reset_scene()

    def click(self, x: int | Box | List[Box] = -1, y=-1, move_back=False, name=None, interval=-1, move=True,
              down_time=0.01, after_sleep=0, key='left'):
        if isinstance(x, Box) or isinstance(x, list):
            return self.click_box(x, move_back=move_back, down_time=down_time, after_sleep=after_sleep)
        elif 0 < x < 1 or 0 < y < 1:
            return self.click_relative(x, y, move_back=move_back, move=move, interval=interval, after_sleep=after_sleep,
                                       name=name, down_time=down_time, key=key)
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box(f"{key}_click",
                                  [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click", confidence=-1)],
                                  "green")
        self.executor.interaction.click(x, y, move_back=move_back, name=name, move=move, down_time=down_time, key=key)
        if name:
            self.logger.info(f'{key}_click {name} {x, y} after_sleep {after_sleep}')
        if after_sleep > 0:
            self.sleep(after_sleep)
        self.executor.reset_scene()
        return True

    def back(self, *args, **kwargs):
        self.executor.interaction.back(*args, **kwargs)

    def middle_click(self, *args, **kwargs):
        return self.click(*args, **kwargs, key="middle")

    def right_click(self, *args, **kwargs):
        return self.click(*args, **kwargs, key="right")

    def check_interval(self, interval):
        if interval <= 0:
            return True
        now = time.time()
        if now - self.last_click_time < interval:
            return False
        else:
            self.last_click_time = now
            return True

    def is_adb(self):
        if device := self._executor.device_manager.get_preferred_device():
            return device.get('device') == 'adb' or device.get('device') == 'emulator'

    def is_browser(self):
        if device := self._executor.device_manager.get_preferred_device():
            return device.get('device') == 'browser'

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("mouse_down",
                                  [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click", confidence=-1)], "green",
                                  frame)
        self.executor.reset_scene()
        self.executor.interaction.mouse_down(x, y, name=name, key=key)

    def mouse_up(self, name=None, key="left"):
        communicate.emit_draw_box("mouse_up",
                                  self.box_of_screen(0.5, 0.5, width=0.01, height=0.01, name="mouse_up", confidence=-1),
                                  "green")
        self.executor.interaction.mouse_up(key=key)
        self.executor.reset_scene()

    def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5, settle_time=0):
        self.swipe(int(self.width * from_x), int(self.height * from_y), int(self.width * to_x),
                   int(self.height * to_y), duration, settle_time=settle_time)

    def input_text(self, text):
        name = f"input_text_{text}"
        communicate.emit_draw_box(name, self.box_of_screen(0.5, 0.5, width=0.01, height=0.01, name=name, confidence=-1),
                                  "blue")
        self.executor.interaction.input_text(text)

    @property
    def hwnd(self):
        return self.executor.device_manager.hwnd_window

    def scroll_relative(self, x, y, count):
        self.scroll(int(self.width * x), int(self.height * y), count)

    def scroll(self, x, y, count):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("scroll", [
            Box(x, y, 10, 10,
                name="scroll")], "green", frame)
        # ms = int(duration * 1000)
        self.executor.interaction.scroll(x, y, count)
        self.executor.reset_scene()
        # self.sleep(duration)

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.5, after_sleep=0.1, settle_time=0):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("swipe", [
            Box(min(from_x, to_x), min(from_y, to_y), max(abs(from_x - from_x), 10), max(abs(from_y - to_y), 10),
                name="swipe")], "green", frame)
        ms = int(duration * 1000)
        self.executor.reset_scene()
        self.executor.interaction.swipe(from_x, from_y, to_x, to_y, ms, settle_time=settle_time)
        self.sleep(after_sleep)

    def screenshot(self, name=None, frame=None, show_box=False, frame_box=None):
        if name is None:
            raise ValueError('screenshot name cannot be None')
        communicate.screenshot.emit(self.frame if frame is None else frame, name, show_box, frame_box)

    def click_box_if_name_match(self, boxes, names, relative_x=0.5, relative_y=0.5):
        """
        Clicks on a box from a list of boxes if the box's name matches one of the specified names.
        The box to click is selected based on the order of names provided, with priority given
        to the earliest match in the names list.

        Parameters:
        - boxes (list): A list of box objects. Each box object must have a 'name' attribute.
        - names (str or list): A string or a list of strings representing the name(s) to match against the boxes' names.
        - relative_x (float, optional): The relative X coordinate within the box to click,
                                        as a fraction of the box's width. Defaults to 0.5 (center).
        - relative_y (float, optional): The relative Y coordinate within the box to click,
                                        as a fraction of the box's height. Defaults to 0.5 (center).

        Returns:
        - box: the matched box

        The method attempts to find and click on the highest-priority matching box. If no matches are found,
        or if there are no boxes, the method returns False. This operation is case-sensitive.
        """
        to_click = find_box_by_name(boxes, names)
        if to_click is not None:
            self.logger.info(f"click_box_if_name_match found {to_click}")
            self.click_box(to_click, relative_x, relative_y)
            return to_click

    def box_of_screen(self, x, y, to_x= 1.0, to_y=1.0, width = 0.0, height = 0.0, name=None,
                      hcenter=False, confidence=1.0):
        if name is None:
            name = f"{x} {y} {width} {height}"
        if self.out_of_ratio():
            should_width = self.executor.device_manager.supported_ratio * self.height
            return self.box_of_screen_scaled(should_width, self.height,
                                             x_original=x * should_width,
                                             y_original=self.height * y,
                                             to_x=to_x * should_width,
                                             to_y=to_y * self.height, width_original=width * should_width,
                                             height_original=self.height * height,
                                             name=name, hcenter=hcenter, confidence=confidence)
        else:
            return relative_box(self.executor.method.width, self.executor.method.height, x, y,
                                to_x=to_x, to_y=to_y, width=width, height=height, name=name, confidence=confidence)

    def out_of_ratio(self):
        return self.executor.device_manager.supported_ratio and abs(
            self.width / self.height - self.executor.device_manager.supported_ratio) > 0.01

    def ensure_in_front(self):
        self.executor.device_manager.adb_ensure_in_front()

    def box_of_screen_scaled(self, original_screen_width, original_screen_height, x_original, y_original,
                             to_x = 0, to_y = 0, width_original=0, height_original=0,
                             name=None, hcenter=False, confidence=1.0):
        if width_original == 0:
            width_original = to_x - x_original
        if height_original == 0:
            height_original = to_y - y_original
        x, y, w, h, scale = adjust_coordinates(x_original, y_original, width_original, height_original,
                                               self.screen_width, self.screen_height, original_screen_width,
                                               original_screen_height, hcenter=hcenter)
        return Box(x, y, w, h, name=name, confidence=confidence)

    def height_of_screen(self, percent):
        return int(percent * self.executor.method.height)

    @property
    def screen_width(self):
        return self.executor.method.width

    @property
    def screen_height(self):
        return self.executor.method.height

    def width_of_screen(self, percent):
        return int(percent * self.executor.method.width)

    def click_relative(self, x, y, move_back=False, hcenter=False, move=True, after_sleep=0, name=None, interval=-1,
                       down_time=0.02,
                       key="left"):
        if self.out_of_ratio():
            should_width = self.executor.device_manager.supported_ratio * self.height
            x, y, w, h, scale = adjust_coordinates(x * should_width, y * self.height, 0, 0,
                                                   self.screen_width, self.screen_height, should_width,
                                                   self.height, hcenter=hcenter)
        else:
            x, y = int(self.width * x), int(self.height * y)
        self.click(x, y, move_back, name=name, move=move, down_time=down_time, after_sleep=after_sleep,
                   interval=interval, key=key)

    def middle_click_relative(self, x, y, move_back=False, down_time=0.01):
        self.middle_click(int(self.width * x), int(self.height * y), move_back,
                          name=f'relative({x:.2f}, {y:.2f})', down_time=down_time)

    @property
    def height(self):
        return self.executor.method.height

    @property
    def width(self):
        return self.executor.method.width

    def move_relative(self, x, y):
        self.move(int(self.width * x), int(self.height * y))

    def move(self, x, y):
        self.executor.interaction.move(x, y)
        self.executor.reset_scene()

    def click_box(self, box: Box | List[Box] = None, relative_x=0.5, relative_y=0.5, raise_if_not_found=False,
                  move_back=False, down_time=0.01, after_sleep=1):
        if isinstance(box, list):
            if len(box) > 0:
                box = box[0]

        if isinstance(box, str):
            box = self.get_box_by_name(box)

        if not box:
            self.logger.error(f"click_box box is None")
            if raise_if_not_found:
                raise Exception(f"click_box box is None")
            return
        x, y = box.relative_with_variance(relative_x, relative_y)
        return self.click(x, y, name=box.name, move_back=move_back, down_time=down_time, after_sleep=after_sleep)

    def wait_scene(self, scene_type=None, time_out=0, pre_action=None, post_action=None):
        return self.executor.wait_scene(scene_type, time_out, pre_action, post_action)

    def sleep(self, timeout):
        self.executor.sleep(timeout)
        return True

    def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0):
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box("send_key",
                                  [Box(max(0, 0), max(0, 0), 20, 20, name="send_key_" + str(key), confidence=-1)],
                                  "green")
        self.executor.reset_scene()
        self.executor.interaction.send_key(key, down_time)
        if after_sleep > 0:
            self.sleep(after_sleep)
        return True

    def get_global_config(self, option):
        return self.executor.global_config.get_config(option)

    def get_global_config_desc(self, option):
        return self.executor.global_config.get_config_desc(option)

    def send_key_down(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_down(key)

    def send_key_up(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_up(key)

    def wait_until(self, condition, time_out=0, pre_action=None, post_action=None, settle_time=-1,
                   raise_if_not_found=False):
        return self.executor.wait_condition(condition, time_out, pre_action, post_action, settle_time=settle_time,
                                            raise_if_not_found=raise_if_not_found)

    def wait_click_box(self, condition, time_out=0, pre_action=None, post_action=None, raise_if_not_found=False):
        target = self.wait_until(condition, time_out, pre_action, post_action)
        self.click_box(box=target, raise_if_not_found=raise_if_not_found)
        return target

    def next_frame(self):
        return self.executor.next_frame()

    def adb_ui_dump(self):
        return self.executor.device_manager.adb_ui_dump()

    @property
    def frame(self):
        return self.executor.frame

    @staticmethod
    def draw_boxes(feature_name=None, boxes=None, color="red", debug=True):
        communicate.emit_draw_box(feature_name, boxes, color, debug=debug)

    def clear_box(self):
        communicate.clear_box.emit()

    def calculate_color_percentage(self, color, box: Box | str):
        box = self.get_box_by_name(box)
        percentage = calculate_color_percentage(self.frame, color, box)
        box.confidence = percentage
        self.draw_boxes(box.name, box)
        return percentage

    def adb_shell(self, *args, **kwargs):
        return self.executor.device_manager.shell(*args, **kwargs)

cdef class TriggerTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config['_enabled'] = False
        self.trigger_interval = 0

    def on_create(self):
        self._enabled = self.config.get('_enabled', False)

    def get_status(self):
        if self.enabled:
            return "Enabled"
        else:
            return "Disabled"

    def enable(self):
        super().enable()
        self.config['_enabled'] = True

    def disable(self):
        super().disable()
        self.config['_enabled'] = False

cdef class FindFeature(ExecutorOperation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def find_feature(self, feature_name=None, horizontal_variance=0, vertical_variance=0, threshold=0,
                     use_gray_scale=False, x=-1, y=-1, to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0,
                     canny_higher=0, frame_processor=None, template=None, match_method=cv2.TM_CCOEFF_NORMED,
                     screenshot=False,
                     mask_function=None, frame=None) -> List[Box]:
        if box and isinstance(box, str):
            box = self.get_box_by_name(box)
        return self.executor.feature_set.find_feature(frame if frame is not None else self.executor.frame, feature_name,
                                                      horizontal_variance,
                                                      vertical_variance,
                                                      threshold, use_gray_scale, x, y, to_x, to_y, width, height,
                                                      box=box, match_method=match_method, screenshot=screenshot,
                                                      canny_lower=canny_lower, canny_higher=canny_higher,
                                                      frame_processor=frame_processor,
                                                      template=template, mask_function=mask_function)

    def get_feature_by_name(self, name):
        if self.executor.feature_set:
            return self.executor.feature_set.get_feature_by_name(self.frame, name)
        raise ValueError(f"No feature found for name {name}")

    def get_box_by_name(self, name):
        if isinstance(name, Box):
            return name
        if self.executor.feature_set:
            box = self.executor.feature_set.get_box_by_name(self.frame, name)
            if box:
                return box
        if name == 'right':
            return self.box_of_screen(0.5, 0, 1, 1)
        elif name == 'bottom_right':
            return self.box_of_screen(0.5, 0.5, 1, 1)
        elif name == 'top_right':
            return self.box_of_screen(0.5, 0, 1, 0.5)
        elif name == 'left':
            return self.box_of_screen(0, 0, 0.5, 1)
        elif name == 'bottom_left':
            return self.box_of_screen(0, 0.5, 0.5, 1)
        elif name == 'top_left':
            return self.box_of_screen(0, 0, 0.5, 0.5)
        elif name == 'bottom':
            return self.box_of_screen(0, 0.5, 1, 1)
        elif name == 'top':
            return self.box_of_screen(0, 0, 1, 0.5)
        else:
            raise ValueError(f"No box found for category {name}")

    def find_feature_and_set(self, features, horizontal_variance=0, vertical_variance=0, threshold=0):
        ret = True
        if features is None:
            raise Exception("features cannot be None")
        if isinstance(features, str):
            features = [features]
        for feature in features:
            result = self.find_one(feature, horizontal_variance, vertical_variance, threshold)
            if result is None:
                ret = False
            setattr(self, feature, result)
        return ret

    def wait_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0,
                     time_out=0, pre_action=None, post_action=None, use_gray_scale=False, box=None,
                     raise_if_not_found=False, canny_lower=0, canny_higher=0, settle_time=-1,
                     frame_processor=None):
        return self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold,
                                  use_gray_scale=use_gray_scale, box=box,
                                  canny_lower=canny_lower, canny_higher=canny_higher,
                                  frame_processor=frame_processor),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action,
            raise_if_not_found=raise_if_not_found, settle_time=settle_time)

    def wait_click_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0, relative_x=0.5,
                           relative_y=0.5,
                           time_out=0, pre_action=None, post_action=None, box=None, raise_if_not_found=True,
                           use_gray_scale=False, canny_lower=0, canny_higher=0, click_after_delay=0, settle_time=-1,
                           after_sleep=0):
        box = self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold, box=box,
                                  use_gray_scale=use_gray_scale, canny_lower=canny_lower, canny_higher=canny_higher),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action, raise_if_not_found=raise_if_not_found,
            settle_time=settle_time)
        if box is not None:
            if click_after_delay > 0:
                self.sleep(click_after_delay)
            self.click_box(box, relative_x, relative_y, after_sleep=after_sleep)
            return True
        return False

    def find_one(self, feature_name=None, horizontal_variance=0, vertical_variance=0, threshold=0,
                 use_gray_scale=False, box=None, canny_lower=0, canny_higher=0,
                 frame_processor=None, template=None, mask_function=None, frame=None, match_method=cv2.TM_CCOEFF_NORMED,
                 screenshot=False) -> Box:
        boxes = self.find_feature(feature_name=feature_name, horizontal_variance=horizontal_variance,
                                  vertical_variance=vertical_variance, threshold=threshold,
                                  use_gray_scale=use_gray_scale, box=box, canny_lower=canny_lower,
                                  canny_higher=canny_higher, match_method=match_method, screenshot=screenshot,
                                  frame_processor=frame_processor, template=template, mask_function=mask_function,
                                  frame=frame)
        if len(boxes) > 0:
            if len(boxes) > 1:
                logger.warning(f"find_one:found {feature_name} too many {len(boxes)}")
            highest_box = find_highest_confidence_box(boxes)
            return highest_box

    def on_feature(self, boxes):
        pass

    def feature_exists(self, feature_name: str) -> bool:
        return self.executor.feature_set.feature_exists(feature_name)

    def find_best_match_in_box(self, box, to_find, threshold, use_gray_scale=False,
                               canny_lower=0, canny_higher=0,
                               frame_processor=None, mask_function=None):
        max_conf = 0
        max_box = None
        for feature_name in to_find:
            feature = self.find_one(feature_name, box=box,
                                    threshold=threshold, use_gray_scale=use_gray_scale,
                                    canny_lower=canny_lower, canny_higher=canny_higher,
                                    frame_processor=frame_processor, mask_function=mask_function)
            if feature and feature.confidence > max_conf:
                max_conf = feature.confidence
                max_box = feature
        # logger.debug(f'find_best_match_in_box: {max_box} {max_conf}')
        return max_box

    def find_first_match_in_box(self, box, to_find, threshold, use_gray_scale=False,
                                canny_lower=0, canny_higher=0,
                                frame_processor=None, mask_function=None):
        for feature_name in to_find:
            feature = self.find_one(feature_name, box=box,
                                    threshold=threshold, use_gray_scale=use_gray_scale,
                                    canny_lower=canny_lower, canny_higher=canny_higher,
                                    frame_processor=frame_processor, mask_function=mask_function)
            if feature:
                logger.debug(f'find_first_match_in_box: {feature}')
                return feature

cdef class OCR(FindFeature):
    """
    Optical Character Recognition (OCR) class for detecting and recognizing text within images.

    Attributes:
        ocr_default_threshold (float): The default confidence threshold for OCR results.
        ocr_target_height (int): The target height for resizing images before OCR.
    """

    cdef public float ocr_default_threshold
    cdef bint log_debug

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_threshold(self, lib, threshold):
        if threshold > 0:
            return threshold
        else:
            return self.executor.config.get('ocr').get(lib).get('default_threshold', 0.8)

    cpdef list ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, match=None,
                   int width=0, int height=0, object box=None, name=None,
                   double threshold=0,
                   object frame=None, int target_height=0, bint use_grayscale=False, bint log=False,
                   frame_processor=None, lib='default'):
        """
        Performs OCR on a region of an image.

        Args:
            x (double): Relative x-coordinate of the top-left corner of the region.
            y (double): Relative y-coordinate of the top-left corner of the region.
            to_x (double): Relative x-coordinate of the bottom-right corner of the region.
            to_y (double): Relative y-coordinate of the bottom-right corner of the region.
            match (str | List[str] | Pattern[str] | List[Pattern[str]] | None): A string, list of strings, regex pattern, or list of regex patterns to match against the recognized text.
            width (int): Width of the region in pixels.
            height (int): Height of the region in pixels.
            box (Box): A Box object defining the region.
            name (str): A name for the region.
            threshold (double): The confidence threshold for OCR results.
            frame (np.ndarray): The image frame to perform OCR on.
            target_height (int): The target height for resizing the image before OCR.
            use_grayscale (bool): Whether to convert the image to grayscale before OCR.
            log (bool): Whether to log the OCR results.

        Returns:
            list: A list of Box objects representing the detected text regions, sorted by y-coordinate.
                 Returns an empty list if no text is detected or no matches are found.

        Raises:
            Exception: If no image frame is provided.
        """
        if box and isinstance(box, str):
            box = self.get_box_by_name(box)
        if self.executor.paused:
            self.executor.sleep(1)
        if threshold == 0:
            threshold = self.ocr_default_threshold
        start = time.time()
        match = self.fix_match_regex(match)
        if frame is not None:
            image = frame
        else:
            image = self.executor.frame
        frame_height, frame_width = image.shape[0], image.shape[1]
        if image is None:
            raise Exception("ocr no frame")
        else:
            if box is None:
                box = relative_box(frame_width, frame_height, x, y, to_x, to_y, width, height, name)
            if box is not None:
                image = image[box.y:box.y + box.height, box.x:box.x + box.width]
                if not box.name and match:
                    box.name = str(match)
            if use_grayscale:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            image, scale_factor = resize_image(image, frame_height, target_height)
            if frame_processor is not None:
                image = frame_processor(image)
            detected_boxes, ocr_boxes = self.ocr_fun(lib)(box, image, match, scale_factor, threshold, lib)

            communicate.emit_draw_box("ocr" + join_list_elements(name), detected_boxes, "red")
            communicate.emit_draw_box("ocr_zone" + join_list_elements(name), [box] if box else [],
                                      "blue")  # ensure list for drawing

            if log and self.debug:
                self.screenshot('ocr', frame=image, show_box=True, frame_box=box)
            if log:
                level = logger.info
            elif self.log_debug and self.debug:
                level = logger.debug
            else:
                level = None
            if level:
                level(
                    f"ocr_zone {box} found result: {detected_boxes}) time: {(time.time() - start):.2f} scale_factor: {scale_factor:.2f} target_height:{target_height} resized_shape:{image.shape} all_boxes: {ocr_boxes}")
            if level and not detected_boxes and ocr_boxes:
                level(f'ocr detected but no match: {match} {ocr_boxes}')
            return sort_boxes(detected_boxes)

    def ocr_fun(self, lib):
        lib_name = self.executor.config.get('ocr').get(lib).get('lib')
        if lib_name == 'paddleocr':
            return self.paddle_ocr
        elif lib_name == 'dgocr':
            return self.duguang_ocr
        elif lib_name == 'onnxocr':
            return self.onnx_ocr
        else:
            return self.rapid_ocr

    cdef object fix_match_regex(self, match):
        if match and self.executor.ocr_po_translation:
            if not isinstance(match, list):
                match = [match]
            for i in range(len(match)):
                if isinstance(match[i], re.Pattern):
                    original_pattern_object = match[i]
                    original_pattern_string = original_pattern_object.pattern
                    original_flags = original_pattern_object.flags

                    # 2. Translate the ORIGINAL PATTERN STRING
                    translated_pattern_string = self.executor.ocr_po_translation.gettext(original_pattern_string)
                    # logger.debug(f'translate regex {original_pattern_string} {translated_pattern_string}')
                    if isinstance(translated_pattern_string, str):
                        match[i] = re.compile(translated_pattern_string, original_flags)
                    else:
                        logger.warning(
                            f"Warning: Translation failed for pattern: {original_pattern_string} {translated_pattern_string}. Keeping original.")
        return match

    cdef str fix_texts(self, detected_boxes):
        for detected_box in detected_boxes:
            detected_box.name = detected_box.name.strip()
            if self.executor.ocr_po_translation is not None:
                fix = self.executor.ocr_po_translation.gettext(detected_box.name)
                if fix != detected_box.name:
                    detected_box.name = fix
                else:
                    no_space = detected_box.name.replace(" ", "")
                    fix = self.executor.ocr_po_translation.gettext(no_space)
                    if fix != no_space:
                        detected_box.name = fix
            if fix := self.executor.text_fix.get(detected_box.name):
                logger.debug(f'text_fixed {detected_box.name} -> {fix}')
                detected_box.name = fix

    cpdef add_text_fix(self, fix):
        """Adds text fixes to the text_fix dictionary."""
        self.executor.text_fix.update(fix)

    def onnx_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            result = self.executor.ocr_lib(lib).ocr(image)
        except Exception as e:
            logger.error('onnx_ocr', e)
            self.screenshot('onnx_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        if result[0] is not None:
            for i in range(len(result[0])):
                pos = result[0][i][0]
                text = result[0][i][1][0]
                confidence = result[0][i][1][1]
                width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    if self.debug:
                        self.screenshot('negative_text', frame=image)
                    continue
                detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
                if detected_box:
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def rapid_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            result = self.executor.ocr_lib(lib)(image, use_det=True, use_cls=False, use_rec=True)
        except Exception as e:
            logger.error('rapid_ocr_exception', e)
            self.screenshot('rapid_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        if result.boxes is not None:
            for i in range(len(result.boxes)):
                pos = result.boxes[i]
                text = result.txts[i]
                confidence = result.scores[i]
                width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    if self.debug:
                        self.screenshot('negative_text', frame=image)
                    continue
                detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
                if detected_box:
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def duguang_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        try:
            results = self.executor.ocr_lib(lib).run(image)
        except Exception as e:
            logger.error('duguang_ocr_exception', e)
            self.screenshot('duguang_ocr_exception', frame=image)
            raise e
        cdef list detected_boxes = []
        # logger.debug(f'rapid_ocr result {result}')
        # Process the results and create Box objects
        for result in results:
            pos = result[0]
            text, confidence = result[1]
            width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
            if width <= 0 or height <= 0:
                logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                if self.debug:
                    self.screenshot('negative_text', frame=image)
                continue
            detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
            # logger.debug(f'rapid_ocr {text} {box} {confidence} {threshold} detected_box {detected_box}')
            if detected_box:
                detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def paddle_ocr(self, object box, object image, match, double scale_factor, double threshold, lib):
        start = time.time()
        cdef results = self.executor.ocr_lib(lib).predict(image)
        cdef list detected_boxes = []
        # Process the results and create Box objects
        if results:
            result = results[0]

            for idx in range(len(result['rec_texts'])):
                pos = result['rec_boxes'][idx]
                text = result['rec_texts'][idx]
                confidence = result['rec_scores'][idx]

                width, height = round(pos[2] - pos[0]), round(pos[3] - pos[1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    continue
                if confidence >= threshold:
                    detected_box = Box(pos[0], pos[1], width, height, confidence, text)
                    scale_box(detected_box, scale_factor)
                    if box is not None:
                        detected_box.x += box.x
                        detected_box.y += box.y
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        self.fix_texts(detected_boxes)
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    cdef get_box(self, object box, double confidence, int height, pos, double scale_factor, text, double threshold,
                 int width):
        detected_box = None
        if confidence >= threshold:
            detected_box = Box(pos[0][0], pos[0][1], width, height, confidence, text)
            scale_box(detected_box, scale_factor)
            if box is not None:
                detected_box.x += box.x
                detected_box.y += box.y
        return detected_box

    cpdef wait_click_ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, int width=0, int height=0,
                         box=None, name=None,
                         match=None, double threshold=0, frame=None, int target_height=0, int time_out=0,
                         bint raise_if_not_found=False, recheck_time=0, after_sleep=0, post_action=None, log=False,
                         settle_time=-1, lib="default"):

        result = self.wait_ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                               threshold=threshold, frame=frame, target_height=target_height, time_out=time_out,
                               raise_if_not_found=raise_if_not_found, post_action=post_action, log=log,
                               settle_time=settle_time, lib=lib)
        if recheck_time > 0:
            self.sleep(1)
            result = self.ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                              threshold=threshold, frame=frame, target_height=target_height, log=log, lib=lib)
        if result is not None:
            self.click_box(result, after_sleep=after_sleep)
            return result
        else:
            logger.warning(f'wait ocr no box {x} {y} {width} {height} {to_x} {to_y} {match}')

    def wait_ocr(self, double x=0, double y=0, double to_x=1, double to_y=1, int width=0, int height=0, name=None,
                 box=None,
                 match=None, double threshold=0, frame=None, int target_height=0, int time_out=0, post_action=None,
                 bint raise_if_not_found=False, log=False, settle_time=-1, lib="default"):
        boxes = self.wait_until(
            lambda: self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                             match=match, threshold=threshold, frame=frame, target_height=target_height, log=log,
                             lib=lib),
            time_out=time_out, post_action=post_action,
            raise_if_not_found=raise_if_not_found, settle_time=settle_time)
        if not boxes and raise_if_not_found:
            logger.error(f'wait_ocr failed, ocr again and log')
            boxes = self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                             threshold=threshold, frame=frame, target_height=target_height, log=True, lib=lib)
        return boxes

cdef tuple resize_image(object image, int frame_height, int target_height):
    """Resizes the image if the original height is significantly larger than the target height."""
    cdef double scale_factor = 1.0
    cdef int original_height = image.shape[0]
    cdef int image_height, image_width, new_width, new_height

    if target_height > 0 and frame_height >= 1.5 * target_height:
        image_height, image_width = image.shape[:2]
        scale_factor = target_height / frame_height
        new_width = <int> round(image_width * scale_factor)
        new_height = <int> round(image_height * scale_factor)
        image = cv2.resize(image, (new_width, new_height))
    return image, scale_factor

cdef void scale_box(object box, double scale_factor):
    """Scales the box coordinates by the given scale factor."""
    if scale_factor != 1:
        box.x = <int> round(box.x / scale_factor)
        box.y = <int> round(box.y / scale_factor)
        box.width = <int> round(box.width / scale_factor)
        box.height = <int> round(box.height / scale_factor)

cdef str join_list_elements(input_object):
    """Joins the elements of a list into a single string."""
    if input_object is None:
        return ''
    elif isinstance(input_object, list):
        return ''.join(map(str, input_object))
    else:
        return str(input_object)

cdef class BaseTask(OCR):
    cdef public str name
    cdef public str description
    cdef public bint _enabled
    cdef public object config
    cdef public object info
    cdef public dict default_config
    cdef public dict config_description
    cdef public dict config_type
    cdef public bint _paused
    cdef public object lock
    cdef public object _handler
    cdef public bint running
    cdef public bint exit_after_task
    cdef public bint trigger_interval
    cdef public double last_trigger_time
    cdef public double start_time
    cdef public object icon
    cdef public list supported_languages
    cdef public str group_name
    cdef public object group_icon
    cdef public double sleep_check_interval
    cdef public double last_sleep_check_time
    cdef public bint in_sleep_check

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = self.__class__.__name__
        self.description = ""
        self._enabled = False
        self.config = None
        self.exit_after_task = False
        self.info = {}
        self.default_config = {}
        self.global_config_names = []
        self.config_description = {}
        self.config_type = {}
        self.supported_languages = []
        self._paused = False
        self.lock = threading.Lock()
        self._handler = None
        self.running = False
        self.trigger_interval = 0
        self.last_trigger_time = 0
        self.start_time = 0
        self.icon = None
        self.group_name = None
        self.group_icon = FluentIcon.SYNC
        self.first_run_alert = None
        self.show_create_shortcut = False
        self.sleep_check_interval = -1
        self.last_sleep_check_time = 0
        self.in_sleep_check = False

    def run_task_by_class(self, cls):
        task = self.get_task_by_class(cls)
        old_ifo = task.info
        task.info = self.info
        try:
            task.run()
        except Exception as e:
            self.log_error(f'run_task_by_class {cls}', e)
            task.info = old_ifo
            raise e
        task.info = old_ifo

    def post_init(self):
        pass

    def create_shortcut(self):
        index = self.executor.onetime_tasks.index(self) + 1
        path = create_shortcut(None, f' {self.name}', arguments=f"-t {index}")
        if path:
            path2 = create_shortcut(None, f' {self.name} exit_after', arguments=f"-t {index} -e")
            subprocess.Popen(r'explorer /select,"{}"'.format(path))

    def sleep_check(self):
        pass

    def tr(self, message):
        return self.app.tr(message)

    def should_trigger(self):
        if self.trigger_interval == 0:
            return True
        now = time.time()
        time_diff = now - self.last_trigger_time
        if time_diff > self.trigger_interval:
            self.last_trigger_time = now
            return True
        return False

    def add_first_run_alert(self, first_run_alert):
        self.default_config.update({'_first_run_alert': ""})
        self.first_run_alert = first_run_alert

    def add_exit_after_config(self):
        self.default_config.update({'Exit After Task': False})
        self.config_description.update(
            {'Exit After Task': 'Exit the Game and the App after Successfully Executing the Task'})

    def get_status(self):
        if self.running:
            return "Running"
        elif self.enabled:
            if self.paused:
                return "Paused"
            else:
                return "In Queue"
        else:
            return "Not Started"

    def enable(self):
        if not self._enabled:
            self._enabled = True
            self.info_clear()
            self.executor.interaction.on_run()
            logger.info(f'enabled task {self}')
        communicate.task.emit(self)

    @property
    def handler(self) -> Handler:
        with self.lock:
            if self._handler is None:
                self._handler = Handler(self.executor.exit_event, __name__)
            return self._handler

    def pause(self):
        if isinstance(self, TriggerTask):
            self.executor.pause()
        else:
            self.executor.pause(self)
            self._paused = True
            communicate.task.emit(self)
        if self.executor.is_executor_thread():
            self.sleep(1)

    def unpause(self):
        self._paused = False
        self.executor.start()
        communicate.task.emit(self)

    @property
    def paused(self):
        return self._paused

    def log_info(self, message, notify=False):
        self.logger.info(message)
        self.info_set("Log", message)
        if notify:
            self.notification(message, tray=True)

    def log_debug(self, message, notify=False):
        self.logger.debug(message)
        if notify:
            self.notification(message, tray=True)

    def log_error(self, message, exception=None, notify=False):
        self.logger.error(message, exception)
        if exception is not None:
            if len(exception.args) > 0:
                message += exception.args[0]
            else:
                message += str(exception)
        self.info_set("Error", message)
        if notify:
            self.notification(message, error=True, tray=True)

    def go_to_tab(self, tab):
        self.log_info(f"go to tab {tab}")
        communicate.tab.emit(tab)

    def notification(self, message, title=None, error=False, tray=False, show_tab=None):
        communicate.notification.emit(message, title, error, tray, show_tab)

    @property
    def enabled(self):
        return self._enabled

    def info_clear(self):
        self.info.clear()

    def info_incr(self, key, inc=1):
        # If the key is in the dictionary, get its value. If not, return 0.
        value = self.info.get(key, 0)
        # Increment the value
        value += inc
        # Store the incremented value back in the dictionary
        self.info[key] = value

    def info_add_to_list(self, key, item):
        value = self.info.get(key, [])
        if isinstance(item, list):
            value += item
        else:
            value.append(item)
        self.info[key] = value

    def info_set(self, key, value):
        if key != 'Log' and key != 'Error':
            self.logger.info(f'info_set {key} {value}')
        self.info[key] = value

    def info_get(self, *args, **kwargs):
        return self.info.get(*args, **kwargs)

    def info_add(self, key, count=1):
        self.info[key] = self.info.get(key, 0) + count

    def load_config(self):
        self.config = Config(self.__class__.__name__, self.default_config, validator=self.validate)

    def validate(self, key, value):
        message = self.validate_config(key, value)
        if message:
            return False, message
        else:
            return True, None

    def validate_config(self, key, value):
        pass

    def disable(self):
        self._enabled = False
        communicate.task.emit(self)

    @property
    def hwnd_title(self):
        if self.executor.device_manager.hwnd_window:
            return self.executor.device_manager.hwnd_window.hwnd_title
        else:
            return ""

    def run(self):
        pass

    def trigger(self):
        return True

    def on_destroy(self):
        pass

    def on_create(self):
        pass

    def set_executor(self, executor):
        self.load_config()
        self.on_create()

    def find_boxes(self, boxes, match=None, boundary=None):
        if match:
            boxes = find_boxes_by_name(boxes, match)
        if boundary:
            box = self.get_box_by_name(boundary) if isinstance(boundary, str) else boundary
            boxes = find_boxes_within_boundary(boxes, box)
        return boxes
