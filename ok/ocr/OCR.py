import time
from typing import List, Pattern

import cv2

from ok.feature.Box import Box, sort_boxes, find_boxes_by_name, relative_box
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class OCR:
    executor = None
    ocr_default_threshold = 0.8
    ocr_target_height = 0
    ocr_lib = ""

    def ocr(self, x=0, y=0, to_x=1, to_y=1, match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None,
            width=0, height=0, box: Box = None, name=None,
            threshold=0,
            frame=None, target_height=0, use_grayscale=False, log=False):
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
            if use_grayscale:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            image, scale_factor = resize_image(image, original_height, target_height)
            if type(self.executor.ocr).__name__ == "PaddleOCR":  # easy ocr
                detected_boxes, ocr_boxes = self.paddle_ocr(box, image, match, scale_factor, threshold)
            else:
                detected_boxes, ocr_boxes = self.rapid_ocr(box, image, match, scale_factor, threshold)

            communicate.emit_draw_box("ocr" + name if name else "", detected_boxes, "red")
            communicate.emit_draw_box("ocr_zone" + name if name else "", box, "blue")
            if log:
                logger.info(
                    f"ocr_zone {box} found result: {detected_boxes}) time: {(time.time() - start):.2f} scale_factor: {scale_factor:.2f}")
            if log and not detected_boxes and ocr_boxes:
                logger.info(f'ocr detected but no match: {match} {ocr_boxes}')
            return sort_boxes(detected_boxes)

    def rapid_ocr(self, box, image, match, scale_factor, threshold):
        result, _ = self.executor.ocr(image, use_det=True, use_cls=False, use_rec=True)
        detected_boxes = []
        ocr_boxes = None
        # Process the results and create Box objects
        if result is not None:
            for res in result:
                pos = res[0]
                text = res[1]
                confidence = res[2]
                width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                if width <= 0 or height <= 0:
                    logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                    continue
                detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                if detected_box:
                    detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def paddle_ocr(self, box, image, match, scale_factor, threshold):
        result = self.executor.ocr.ocr(image, det=True,
                                       rec=True,
                                       cls=False)
        detected_boxes = []
        ocr_boxes = None
        # Process the results and create Box objects
        if result:
            for idx in range(len(result)):
                r = result[idx]
                if r:
                    for res in r:
                        pos = res[0]
                        text = res[1][0]
                        confidence = res[1][1]
                        width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
                        if width <= 0 or height <= 0:
                            logger.error(f'ocr result negative box {text} {confidence} {width}x{height} pos:{pos}')
                            continue
                        detected_box = self.get_box(box, confidence, height, pos, scale_factor, text, threshold, width)
                        if detected_box:
                            detected_boxes.append(detected_box)
        ocr_boxes = detected_boxes
        if match is not None:
            detected_boxes = find_boxes_by_name(detected_boxes, match)
        return detected_boxes, ocr_boxes

    def get_box(self, box, confidence, height, pos, scale_factor, text, threshold, width):
        detected_box = None
        if confidence >= threshold:
            detected_box = Box(pos[0][0], pos[0][1], width,
                               height,
                               confidence, text)
            scale_box(detected_box, scale_factor)
            if box is not None:
                detected_box.x += box.x
                detected_box.y += box.y
        return detected_box

    def wait_click_ocr(self, x=0, y=0, to_x=1, to_y=1, width=0, height=0, box=None, name=None,
                       match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None, threshold=0,
                       frame=None, target_height=0, time_out=0, raise_if_not_found=False):
        box = self.wait_ocr(x, y, width=width, height=height, to_x=to_x, to_y=to_y, box=box, name=name, match=match,
                            threshold=threshold,
                            frame=frame, target_height=target_height, time_out=time_out,
                            raise_if_not_found=raise_if_not_found)
        if box is not None:
            self.click_box(box)
            return box
        else:
            logger.warning(f'wait ocr no box {x} {y} {width} {height} {to_x} {to_y} {match}')

    def wait_ocr(self, x=0, y=0, to_x=1, to_y=1, width=0, height=0, name=None, box=None,
                 match: str | List[str] | Pattern[str] | List[Pattern[str]] | None = None, threshold=0,
                 frame=None, target_height=0, time_out=0, raise_if_not_found=False):
        return self.wait_until(lambda:
                               self.ocr(x, y, to_x=to_x, to_y=to_y, width=width, height=height, box=box, name=name,
                                        match=match,
                                        threshold=threshold,
                                        frame=frame, target_height=target_height), time_out=time_out,
                               raise_if_not_found=raise_if_not_found)


def resize_image(image, original_height, target_height):
    scale_factor = 1
    if target_height > 0 and original_height >= 1.5 * target_height:
        image_height, image_width = image.shape[:2]
        # times = int(original_height / target_height)
        # scale_factor = 1 / times
        scale_factor = target_height / original_height
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
