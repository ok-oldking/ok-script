import time

import cv2

from ok.feature.Box import Box, sort_boxes, find_boxes_by_name
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class OCR:
    executor = None
    ocr_default_threshold = 0.5
    ocr_target_height = 0

    def ocr(self, box: Box = None, match=None, threshold=0, frame=None, target_height=0):
        if self.paused:
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
            original_height = image.shape[0]
            if box is not None:
                x, y, w, h = box.x, box.y, box.width, box.height
                image = image[y:y + h, x:x + w]

            image, scale_factor = resize_image(image, original_height, target_height)

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

    def find_text(self, text, box: Box = None, confidence=0):
        for result in self.ocr(box, confidence):
            if result.name == text:
                return result


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
