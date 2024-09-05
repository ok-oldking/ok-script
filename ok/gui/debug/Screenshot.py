import os
import queue
import threading
import time
from datetime import datetime

import cv2
from PIL import Image, ImageFont, ImageDraw
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

import ok.gui
from ok.feature.Box import Box
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.util.path import find_first_existing_file, clear_folder, sanitize_filename, \
    get_relative_path

logger = get_logger(__name__)


class Screenshot(QObject):

    def __init__(self, exit_event):
        super().__init__()
        self.queue = []
        self.time_to_expire = 4
        self.ui_dict = {}
        self.color_map = {
            "red": QColor(255, 0, 0),  # RGB for red
            "green": QColor(0, 255, 0),  # RGB for green
            "blue": QColor(0, 0, 255)  # RGB for blue
        }
        self.exit_event = exit_event
        communicate.draw_box.connect(self.draw_box)
        communicate.screenshot.connect(self.screenshot)
        self.click_screenshot_folder = get_relative_path(
            ok.gui.ok.config.get("click_screenshots_folder")) if ok.gui.ok.config.get(
            "click_screenshots_folder") else None
        self.screenshot_folder = get_relative_path(ok.gui.ok.config.get("screenshots_folder"))
        logger.debug(f"init Screenshot {self.screenshot_folder} {self.click_screenshot_folder}")
        if self.click_screenshot_folder is not None or self.screenshot_folder is not None:
            self.task_queue = queue.Queue()
            self.exit_event.bind_queue(self.task_queue)
            self.thread = threading.Thread(target=self._worker, name="screenshot")
            self.thread.start()
            fonts_dir = os.path.join(os.environ['WINDIR'], 'Fonts')
            font = find_first_existing_file(
                ['msyh.ttc', 'msyh.ttf', 'simsun.ttf', 'simsun.ttc', 'arial.ttf', 'arial.ttc'], fonts_dir)
            if os.path.exists(font):
                logger.debug(f"load font {font}")
                self.pil_font = ImageFont.truetype(font, 20)
            else:
                logger.debug("load default font")
                self.pil_font = ImageFont.load_default(20)
            clear_folder(self.click_screenshot_folder)
            clear_folder(self.screenshot_folder)
        else:
            self.task_queue = None

    def screenshot(self, frame, name):
        if self.screenshot_folder is not None and frame is not None:
            self.add_task(frame, self.screenshot_folder, name)

    def draw_box(self, key: str = None, boxes=None, color="red", frame=None):
        if boxes is None:
            return
        if isinstance(boxes, Box):
            boxes = [boxes]
        if len(boxes) == 0:
            return
        if key is None:
            key = boxes[0].name
        timestamp = time.time()
        q_color = self.color_map.get(color, self.color_map.get("red"))
        self.remove_expired()
        if key:
            self.ui_dict[key] = [boxes, timestamp, q_color]
        else:
            for box in boxes:
                self.ui_dict[box.name] = [[box], timestamp, q_color]
        if self.click_screenshot_folder is not None and frame is not None:
            self.add_task(frame, self.click_screenshot_folder, key)

    def remove_expired(self):
        current_time = time.time()
        for key in list(self.ui_dict.keys()):
            # Filter out the old UI elements and keep the remaining ones
            if current_time - self.ui_dict[key][1] > self.time_to_expire:
                del self.ui_dict[key]

    def add_task(self, frame, folder, name=None):
        if self.task_queue is not None:
            self.task_queue.put((frame, self.ui_dict.copy(), folder, f'{get_current_time_formatted()}_{name}'))

    def _worker(self):
        while True and not self.exit_event.is_set():
            task = self.task_queue.get()
            if task is None:
                logger.debug("Task queue get is None quit")
                break
            # Execute the task
            self.generate_screen_shot(task[0], task[1], task[2], task[3])
            self.task_queue.task_done()

    def generate_screen_shot(self, frame, ui_dict, folder, name):
        if folder is None:
            return
        pil_image = self.to_pil_image(frame)
        if pil_image is None:
            return

        originl_name = self.save_pil_image(name + '_original', folder, pil_image)

        if folder == self.click_screenshot_folder:
            # Ensure no fill
            draw = ImageDraw.Draw(pil_image)

            frame_ratio = 1
            if len(ui_dict) > 0:
                for key, value in ui_dict.items():
                    boxes = value[0]
                    color = tuple([int(x) for x in value[2].getRgb()])  # Convert QColor to BGR tuple
                    for box in boxes:
                        width = int(box.width * frame_ratio)
                        height = int(box.height * frame_ratio)
                        if width <= 0 or height <= 0:
                            logger.error(f"box height and width <=0 {box}")
                            continue
                        x = int(box.x * frame_ratio)
                        y = int(box.y * frame_ratio)
                        # Draw a rectangle. Arguments are (x, y, width, height).
                        # Adjust these values according to the desired size and position.
                        draw.rectangle([x, y, x + width, y + height], outline=color, width=2)
                        # Put text
                        draw.text((x, y + height + 8), f"{box.name or key}_{round(box.confidence * 100)}", fill=color,
                                  font=self.pil_font)
            self.save_pil_image(name + '_boxed', folder, pil_image)
        return originl_name

    @staticmethod
    def save_pil_image(name, folder, pil_image):
        name = sanitize_filename(name)
        file = os.path.join(folder, f"{name}.png")
        try:
            pil_image.save(file)
        except OSError:
            file = os.path.join(folder, f"{get_current_time_formatted()}.png")
            pil_image.save(file)
            logger.error(f'save pil_image failed, use only timestamp as name {pil_image}')
        return file

    def stop(self):
        logger.debug(f'stop screenshot')
        if self.task_queue is not None:
            self.task_queue.put(None)

    def to_pil_image(self, frame):
        if frame is None:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def get_current_time_formatted():
    now = datetime.now()
    time_string = now.strftime("%H-%M-%S.") + str(now.microsecond // 1000).zfill(3)
    return time_string
