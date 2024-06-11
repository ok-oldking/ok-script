import sys
from typing import List

from ok.feature.Box import Box


class FindFeature:

    def __init__(self):
        self.feature_set = None
        self.executor = None

    def find_feature(self, feature_name, horizontal_variance=0, vertical_variance=0, threshold=0,
                     use_gray_scale=False, x=-1, y=-1, to_x=-1, to_y=-1, width=-1, height=-1, box=None) -> List[Box]:
        return self.feature_set.find_feature(self.executor.frame, feature_name, horizontal_variance, vertical_variance,
                                             threshold, use_gray_scale, x, y, to_x, to_y, width, height, box=box)

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

    def wait_click_feature(self, feature, horizontal_variance=0, vertical_variance=0, threshold=0, relative_x=0.5,
                           relative_y=0.5,
                           time_out=0, pre_action=None, post_action=None):
        box = self.wait_until(lambda: self.find_one(feature, horizontal_variance, vertical_variance, threshold),
                              time_out,
                              pre_action,
                              post_action)
        if box is not None:
            self.click_box(box, relative_x, relative_y)
            return True
        return False

    def find_one(self, feature_name, horizontal_variance=0, vertical_variance=0, threshold=0,
                 use_gray_scale=False) -> Box:
        boxes = self.find_feature(feature_name, horizontal_variance, vertical_variance, threshold,
                                  use_gray_scale=use_gray_scale)
        if len(boxes) > 0:
            if len(boxes) > 1:
                print(f"find_one:found {feature_name} too many {len(boxes)}", file=sys.stderr)
            return boxes[0]

    def on_feature(self, boxes):
        pass
