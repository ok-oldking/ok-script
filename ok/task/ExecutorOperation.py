import time
from typing import List

from ok.color.Color import calculate_color_percentage, find_color_rgb
from ok.config.ConfigOption import ConfigOption
from ok.feature.Box import Box, find_box_by_name, relative_box
from ok.feature.FeatureSet import adjust_coordinates
from ok.feature.Point import Point
from ok.gui.Communicate import communicate


class ExecutorOperation:
    executor = None

    def __init__(self):
        self.last_click_time = 0

    def exit_is_set(self):
        return self.executor.exit_event.is_set()

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
    def debug(self):
        return self.executor.debug

    def is_scene(self, the_scene):
        return isinstance(self.executor.current_scene, the_scene)

    def reset_scene(self):
        self.executor.reset_scene()

    def click(self, x: int | Box | List[Box] = -1, y=-1, move_back=False, name=None, interval=-1, move=True,
              down_time=0.01, after_sleep=0):
        if isinstance(x, Box) or isinstance(x, list):
            return self.click_box(x, move_back=move_back, down_time=down_time, after_sleep=after_sleep)
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box("click", [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click")], "green",
                                  frame=self.executor.nullable_frame())
        self.executor.interaction.click(x, y, move_back, name=name, move=move, down_time=down_time)
        if after_sleep > 0:
            self.logger.debug(f'click after_sleep: {after_sleep}')
            self.sleep(after_sleep)
        self.executor.reset_scene()
        return True

    def middle_click(self, x: int | Box = -1, y=-1, move_back=False, name=None, interval=-1, down_time=0.01):
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        communicate.emit_draw_box("middle_click", [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click")], "green")
        self.executor.interaction.middle_click(x, y, move_back, name=name, down_time=down_time)
        self.executor.reset_scene()
        return True

    def check_interval(self, interval):
        if interval <= 0:
            return True
        now = time.time()
        if now - self.last_click_time < interval:
            return False
        else:
            self.last_click_time = now
            return True

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("mouse_down", [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click")], "green",
                                  frame)
        self.executor.reset_scene()
        self.executor.interaction.mouse_down(x, y, name=name, key=key)

    def mouse_up(self, name=None, key="left"):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("mouse_up", self.box_of_screen(0.5, 0.5, width=0.01, height=0.01, name="click"),
                                  "green",
                                  frame)
        self.executor.interaction.mouse_up(key=key)
        self.executor.reset_scene()

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        communicate.emit_draw_box("right_click", [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="right_click")],
                                  "green")
        self.executor.reset_scene()
        self.executor.interaction.right_click(x, y, move_back, name=name)

    def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5):
        self.swipe(int(self.width * from_x), int(self.height * from_y), int(self.width * to_x),
                   int(self.height * to_y), duration)

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

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.5):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("swipe", [
            Box(min(from_x, to_x), min(from_y, to_y), max(abs(from_x - from_x), 10), max(abs(from_y - to_y), 10),
                name="swipe")], "green", frame)
        ms = int(duration * 1000)
        self.executor.reset_scene()
        self.executor.interaction.swipe(from_x, from_y, to_x, to_y, ms)
        self.sleep(duration)

    def screenshot(self, name=None, frame=None):
        if name is None:
            raise ValueError('screenshot name cannot be None')
        communicate.screenshot.emit(self.frame if frame is None else frame, name)

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

    def box_of_screen(self, x, y, to_x: float = 1, to_y: float = 1, width: float = 0, height: float = 0, name=None,
                      hcenter=False):
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
                                             name=name, hcenter=hcenter)
        else:
            return relative_box(self.executor.method.width, self.executor.method.height, x, y,
                                to_x=to_x, to_y=to_y, width=width, height=height, name=name)

    def out_of_ratio(self):
        return self.executor.device_manager.supported_ratio and abs(
            self.width / self.height - self.executor.device_manager.supported_ratio) > 0.01

    def box_of_screen_scaled(self, original_screen_width, original_screen_height, x_original, y_original,
                             to_x: int = 0, to_y: int = 0, width_original=0, height_original=0,
                             name=None, hcenter=False):
        if width_original == 0:
            width_original = to_x - x_original
        if height_original == 0:
            height_original = to_y - y_original
        x, y, w, h, scale = adjust_coordinates(x_original, y_original, width_original, height_original,
                                               self.screen_width, self.screen_height, original_screen_width,
                                               original_screen_height, hcenter=hcenter)
        return Box(x, y, w, h, name=name)

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

    def click_relative(self, x, y, move_back=False, hcenter=False, move=True, after_sleep=0):
        if self.out_of_ratio():
            should_width = self.executor.device_manager.supported_ratio * self.height
            x, y, w, h, scale = adjust_coordinates(x * should_width, y * self.height, 0, 0,
                                                   self.screen_width, self.screen_height, should_width,
                                                   self.height, hcenter=hcenter)
        else:
            x, y = int(self.width * x), int(self.height * y)

        self.click(x, y, move_back, name=f'relative({x:.2f}, {y:.2f})', move=move, after_sleep=after_sleep)

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

    def send_key(self, key, down_time=0.02, interval=-1):
        if not self.check_interval(interval):
            self.executor.reset_scene()
            return False
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("send_key", [Box(max(0, 0), max(0, 0), 20, 20, name="send_key_" + str(key))], "green",
                                  frame)
        self.executor.reset_scene()
        self.executor.interaction.send_key(key, down_time)
        return True

    def get_config(self, option: ConfigOption):
        return self.executor.global_config.get_config(option)

    def send_key_down(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_down(key)

    def send_key_up(self, key):
        self.executor.reset_scene()
        self.executor.interaction.send_key_up(key)

    def wait_until(self, condition, time_out=0, pre_action=None, post_action=None, wait_until_before_delay=-1,
                   raise_if_not_found=False):
        return self.executor.wait_condition(condition, time_out, pre_action, post_action, wait_until_before_delay,
                                            raise_if_not_found=raise_if_not_found)

    def wait_click_box(self, condition, time_out=0, pre_action=None, post_action=None, raise_if_not_found=False):
        target = self.wait_until(condition, time_out, pre_action, post_action)
        self.click_box(box=target, raise_if_not_found=raise_if_not_found)
        return target

    def next_frame(self):
        self.executor.next_frame()
        return self.frame

    @property
    def scene(self):
        return self.executor.current_scene

    @property
    def frame(self):
        return self.executor.frame

    @staticmethod
    def draw_boxes(feature_name=None, boxes=None, color="red"):
        communicate.emit_draw_box(feature_name, boxes, color)

    def calculate_color_percentage(self, color, box: Box):
        percentage = calculate_color_percentage(self.frame, color, box)
        box.confidence = percentage
        self.draw_boxes(box.name, box)
        return percentage

    def find_color_rgb(self, rgb: list, point: Point):
        return find_color_rgb(self.frame, rgb, point.x, point.y)

    def adb_shell(self, *args, **kwargs):
        return self.executor.device_manager.shell(*args, **kwargs)
