import queue

from ok.feature.Box import Box, find_box_by_name
from ok.gui.Communicate import communicate


class ExecutorOperation:
    executor = None

    def exit_is_set(self):
        return self.executor.exit_event.is_set()

    def box_in_horizontal_center(self, box, off_percent=0.02):
        if box is None:
            return False
        center = self.executor.method.width / 2
        left = center - box.x
        right = box.x + box.width - center
        if left > 0 and right > 0 and abs(left - right) / box.width < off_percent:
            return True
        else:
            return False

    def new_queue(self):
        q = queue.Queue()
        self.executor.exit_event.bind_queue(q)
        return q

    def is_scene(self, the_scene):
        return isinstance(self.executor.current_scene, the_scene)

    def click(self, x, y, move_back=False):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("click", [Box(max(0, x - 10), max(0, y - 10), 20, 20, name="click")], "green", frame)
        self.executor.reset_scene()
        self.executor.interaction.click(x, y, move_back)

    def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5):
        self.swipe(int(self.width * from_x), int(self.height * from_y), int(self.width * to_x),
                   int(self.height * to_y), duration)

    def swipe(self, from_x, from_y, to_x, to_y, duration=0.5):
        frame = self.executor.nullable_frame()
        communicate.emit_draw_box("click", [
            Box(min(from_x, to_x), min(from_y, to_y), min(abs(from_x - from_x), 10), min(abs(from_y - to_y), 10),
                name="click")], "green", frame)
        ms = int(duration * 1000)
        self.executor.reset_scene()
        self.executor.interaction.swipe(from_x, from_y, to_x, to_y, ms)
        self.sleep(duration)

    def screenshot(self, name=None):
        communicate.screenshot.emit(self.frame, name)

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

    def box_of_screen(self, x, y, width, height, name=None):
        if name is None:
            name = f"{x} {y} {width} {height}"
        return Box(int(x * self.executor.method.width), int(y * self.executor.method.height),
                   int(width * self.executor.method.width), int(height * self.executor.method.height),
                   name=name)

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

    def click_relative(self, x, y, move_back=False):
        self.click(int(self.width * x), int(self.height * y), move_back)

    @property
    def height(self):
        return self.executor.method.height

    @property
    def width(self):
        return self.executor.method.width

    def move_relative(self, x, y):
        self.executor.interaction.move_relative(x, y)

    def click_box(self, box: Box = None, relative_x=0.5, relative_y=0.5, raise_if_not_found=True):
        if box is None:
            self.logger.error(f"click_box box is None")
            if raise_if_not_found:
                raise Exception(f"click_box box is None")
            return
        if isinstance(box, list):
            if len(box) > 0:
                box = box[0]
            else:
                self.logger.error(f"No box")
        x, y = box.relative_with_variance(relative_x, relative_y)
        self.click(x, y)

    def wait_scene(self, scene_type=None, time_out=0, pre_action=None, post_action=None):
        return self.executor.wait_scene(scene_type, time_out, pre_action, post_action)

    def sleep(self, timeout):
        self.executor.reset_scene()
        self.executor.sleep(timeout)

    def send_key(self, key, down_time=0.02):
        self.executor.interaction.send_key(key, down_time)

    def wait_until(self, condition, time_out=0, pre_action=None, post_action=None, wait_until_before_delay=0):
        return self.executor.wait_condition(condition, time_out, pre_action, post_action, wait_until_before_delay)

    def wait_click_box(self, condition, time_out=0, pre_action=None, post_action=None, raise_if_not_found=True):
        target = self.wait_until(condition, time_out, pre_action, post_action)
        self.click_box(box=target, raise_if_not_found=raise_if_not_found)
        return target

    def next_frame(self):
        return self.executor.next_frame()

    @property
    def scene(self):
        return self.executor.current_scene

    @property
    def frame(self):
        return self.executor.frame

    @staticmethod
    def draw_boxes(feature_name=None, boxes=None, color="red"):
        communicate.emit_draw_box(feature_name, boxes, color)
