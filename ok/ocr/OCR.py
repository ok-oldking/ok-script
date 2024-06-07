import time
from typing import List, Pattern

import cv2

from ok.feature.Box import Box, sort_boxes, find_boxes_by_name, relative_box
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class OCR:
    executor = None
    ocr_default_threshold = 0.5
    ocr_target_height = 0

    def ocr(self, x=0, y=0, to_x=1, to_y=1, width=0, height=0, box: Box = None, name=None,
            match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None, threshold=0,
            frame=None, target_height=0):
        if hasattr(self, 'paused') and self.paused:
            self.sleep(1)
        if threshold == 0:
            threshold = self.ocr_default_threshold
        if target_height == 0:
            target_height = self.ocr_target_height
        start = time.time()
        if frame is not None:
            image = frame
        else:
            image = self.frame
        if image is None:
            raise Exception("ocr no frame")
        else:
            if box is None:
                frame_height, frame_width, *_ = image.shape[1], image.shape[0]
                box = relative_box(frame_height, frame_width, x, y, to_x, to_y, width, height, name)
            original_height = image.shape[0]
            if box is not None:
                x, y, w, h = box.x, box.y, box.width, box.height
                image = image[y:y + h, x:x + w]
                if not box.name and match:
                    box.name = str(match)

            image, scale_factor = resize_image(image, original_height, target_height)
            try:
                result, _ = self.executor.ocr(image, use_det=True, use_cls=False, use_rec=True)
            except Exception as e:
                logger.error('ocr_error sleep and retry once', e)
                time.sleep(3)
                result, _ = self.executor.ocr(image, use_det=True, use_cls=False, use_rec=True)
            detected_boxes = []
            # Process the results and create Box objects
            if result is not None:
                for res in result:
                    pos = res[0]
                    text = res[1]
                    confidence = res[2]
                    if confidence >= threshold:
                        detected_box = Box(int(pos[0][0]), int(pos[0][1]), int(pos[2][0] - pos[0][0]),
                                           int(pos[2][1] - pos[0][1]),
                                           confidence, text)
                        scale_box(detected_box, scale_factor)
                        if box is not None:
                            detected_box.x += box.x
                            detected_box.y += box.y
                        detected_boxes.append(detected_box)
                if match is not None:
                    detected_boxes = find_boxes_by_name(detected_boxes, match)

            communicate.emit_draw_box("ocr", detected_boxes, "red")
            communicate.emit_draw_box("ocr_zone", box, "blue")
            logger.debug(
                f"ocr_zone {box} found result: {len(detected_boxes)}) time: {(time.time() - start):.2f} scale_factor: {scale_factor:.2f}")
            return sort_boxes(detected_boxes)

    def wait_click_ocr(self, x=0, y=0, to_x=1, to_y=1, width=0, height=0, box=None, name=None,
                       match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None, threshold=0,
                       frame=None, target_height=0, time_out=0):
        box = self.wait_ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                            threshold=threshold,
                            frame=frame, target_height=target_height, time_out=time_out)
        if box is not None:
            self.click_box(box)
            return box
        else:
            logger.error(f'wait ocr no box {x} {y} {width} {height} {to_x} {to_y} {match}')

    def wait_ocr(self, x=0, y=0, to_x=1, to_y=1, width=0, height=0, name=None, box=None,
                 match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None, threshold=0,
                 frame=None, target_height=0, time_out=0):
        return self.wait_until(lambda:
                               self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                                        match=match,
                                        threshold=threshold,
                                        frame=frame, target_height=target_height), time_out=time_out)


def resize_image(image, original_height, target_height):
    scale_factor = 1
    if target_height > 0 and original_height >= 2 * target_height:
        image_height, image_width = image.shape[:2]
        times = int(original_height / target_height)
        scale_factor = 1 / times
        # Calculate the new width to maintain the aspect ratio
        new_width = round(image_width * scale_factor)
        new_height = round(image_height * scale_factor)
        # Resize the image
        image = cv2.resize(image, (new_width, new_height))
    return image, scale_factor


def scale_box(box, scale_factor):
    if scale_factor != 1:
        box.x = round(box.x / scale_factor)
        box.y = round(box.y / scale_factor)
        box.width = round(box.width / scale_factor)
        box.height = round(box.height / scale_factor)
