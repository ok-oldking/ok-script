import time

from ok.feature.Box import Box, sort_boxes, find_boxes_by_name
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class OCR:
    executor = None
    default_threshold = 0.6

    def ocr(self, box: Box = None, match=None, threshold=0):
        if self.paused:
            self.sleep(1)
        if threshold == 0:
            threshold = self.default_threshold
        start = time.time()
        image = self.frame
        if image is None:
            raise Exception("ocr no frame")
        else:
            if box is not None:
                x, y, w, h = box.x, box.y, box.width, box.height
                image = image[y:y + h, x:x + w]

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
                        if box is not None:
                            detected_box.x += box.x
                            detected_box.y += box.y
                        detected_boxes.append(detected_box)
                if match is not None:
                    detected_boxes = find_boxes_by_name(detected_boxes, match)
            communicate.emit_draw_box("ocr", detected_boxes, "red")
            communicate.emit_draw_box("ocr_zone", box, "blue")
            logger.debug(f"ocr_zone {box} found result: {len(detected_boxes)}) time: {time.time() - start}")
            return sort_boxes(detected_boxes)

    def find_text(self, text, box: Box = None, confidence=0):
        for result in self.ocr(box, confidence):
            if result.name == text:
                return result
