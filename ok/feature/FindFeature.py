import sys
from typing import List

from ok.feature.Box import Box, find_highest_confidence_box
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class FindFeature:

    def __init__(self):
        self.feature_set = None
        self.executor = None

    def find_feature(self, feature_name, horizontal_variance=0, vertical_variance=0, threshold=0,
                     use_gray_scale=False, x=-1, y=-1, to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0,
                     canny_higher=0, inverse_mask_color=None, frame_processor=None, template=None) -> List[Box]:
        return self.feature_set.find_feature(self.executor.frame, feature_name, horizontal_variance, vertical_variance,
                                             threshold, use_gray_scale, x, y, to_x, to_y, width, height, box=box,
                                             canny_lower=canny_lower, canny_higher=canny_higher,
                                             inverse_mask_color=inverse_mask_color, frame_processor=frame_processor,
                                             template=template)

    def get_box_by_name(self, name):
        return self.feature_set.get_box_by_name(self.executor.frame, name)

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

    def wait_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0, wait_until_before_delay=-1,
                     time_out=0, pre_action=None, post_action=None, use_gray_scale=False, box=None,
                     raise_if_not_found=False, canny_lower=0, canny_higher=0, inverse_mask_color=None,
                     frame_processor=None):
        return self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold,
                                  use_gray_scale=use_gray_scale, box=box, inverse_mask_color=inverse_mask_color,
                                  canny_lower=canny_lower, canny_higher=canny_higher,
                                  frame_processor=frame_processor),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action, wait_until_before_delay=wait_until_before_delay,
            raise_if_not_found=raise_if_not_found)

    def wait_click_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0, relative_x=0.5,
                           relative_y=0.5,
                           time_out=0, pre_action=None, post_action=None, box=None, raise_if_not_found=True,
                           use_gray_scale=False, canny_lower=0, canny_higher=0, click_after_delay=0):
        box = self.wait_until(
            lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold, box=box,
                                  use_gray_scale=use_gray_scale, canny_lower=canny_lower, canny_higher=canny_higher),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action, raise_if_not_found=raise_if_not_found)
        if box is not None:
            if click_after_delay > 0:
                self.sleep(click_after_delay)
            self.click_box(box, relative_x, relative_y)
            return True
        return False

    def find_one(self, feature_name, horizontal_variance=0, vertical_variance=0, threshold=0,
                 use_gray_scale=False, box=None, canny_lower=0, canny_higher=0, inverse_mask_color=None,
                 frame_processor=None) -> Box:
        boxes = self.find_feature(feature_name, horizontal_variance, vertical_variance, threshold,
                                  use_gray_scale=use_gray_scale, box=box, canny_lower=canny_lower,
                                  canny_higher=canny_higher, inverse_mask_color=inverse_mask_color,
                                  frame_processor=frame_processor)
        if len(boxes) > 0:
            if len(boxes) > 1:
                logger.warning(f"find_one:found {feature_name} too many {len(boxes)}", file=sys.stderr)
            highest_box = find_highest_confidence_box(boxes)
            return highest_box

    def on_feature(self, boxes):
        pass
