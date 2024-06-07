import json
import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np

from ok.feature.Box import Box, sort_boxes
from ok.feature.Feature import Feature
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.util.path import resource_path

logger = get_logger(__name__)


class FeatureSet:
    # Category_name to OpenCV Mat
    feature_dict: Dict[str, Feature] = {}
    box_dict: Dict[str, Box] = {}
    original_size_dict: Dict[str, tuple[int, int]] = {}  # Store original size (width, height)

    def __init__(self, coco_json: str, default_horizontal_variance=0, default_vertical_variance=0,
                 default_threshold=0.95) -> None:
        self.coco_json = resource_path(coco_json)
        self.coco_folder = os.path.dirname(self.coco_json)
        logger.debug(f'Loading features from {self.coco_json}')
        if default_threshold == 0:
            default_threshold = 0.95
        self.default_threshold = default_threshold
        self.default_horizontal_variance = default_horizontal_variance
        self.default_vertical_variance = default_vertical_variance
        self.process_data()

    def process_data(self) -> None:
        self.feature_dict.clear()
        self.box_dict.clear()
        with open(self.coco_json, 'r') as file:
            data = json.load(file)

        image_map = {image['id']: image['file_name'] for image in data['images']}
        category_map = {category['id']: category['name'] for category in data['categories']}

        for annotation in data['annotations']:
            image_id = annotation['image_id']
            category_id = annotation['category_id']
            bbox = annotation['bbox']

            image_path = str(os.path.join(self.coco_folder, image_map[image_id]))
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f'Could not read image {image_path}')
                continue
            image_height, image_width = image.shape[:2]
            x, y, w, h = map(round, bbox)
            cropped_image = image[y:y + h, x:x + w, :3]

            category_name = category_map[category_id]
            if category_name in self.feature_dict:
                raise ValueError(f"Multiple boxes found for category {category_name}")
            if not category_name.startswith('box_'):
                self.feature_dict[category_name] = Feature(cropped_image, x, y, w, h, image_width, image_height)
                logger.debug(f'Loaded {category_name} {self.feature_dict[category_name]}')
            self.box_dict[category_name] = Box(x, y, w, h, name=category_name)

    def get_box_by_name(self, category_name: str) -> Box:
        if category_name in self.box_dict:
            return self.box_dict[category_name]
        else:
            raise ValueError(f"No box found for category {category_name}")

    def save_images(self, target_folder: str) -> None:
        os.makedirs(target_folder, exist_ok=True)
        for category_name, image in self.feature_dict.items():
            file_name = f"{category_name}.jpg"
            file_path = os.path.join(target_folder, file_name)
            cv2.imwrite(file_path, image.mat)
            print(f"Saved {file_path}")

    def find_one(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
                 vertical_variance: float = 0, threshold=0, use_gray_scale=False) -> Box:
        boxes = self.find_feature(mat, category_name, horizontal_variance=horizontal_variance,
                                  vertical_variance=vertical_variance, threshold=threshold,
                                  use_gray_scale=use_gray_scale)
        if len(boxes) > 1:
            logger.warning(f"find_one:found too many {len(boxes)} return first", file=sys.stderr)
        if len(boxes) >= 1:
            return boxes[0]

    def find_feature(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                     to_x=-1, to_y=-1, width=-1, height=-1) -> List[Box]:
        start = time.time()
        if threshold == 0:
            threshold = self.default_threshold
        if horizontal_variance == 0:
            horizontal_variance = self.default_horizontal_variance
        if vertical_variance == 0:
            vertical_variance = self.default_vertical_variance
        if category_name not in self.feature_dict:
            raise ValueError(f"FeatureSet: " + category_name + " not found in featureDict")

        feature = self.feature_dict[category_name]
        frame_height, frame_width, *_ = mat.shape
        scaling = frame_height / feature.frame_height
        if x != -1 and y != -1:
            if width == -1:
                width = to_x - x
            if height == -1:
                height = to_y - y
            search_x1 = round(x * frame_width)
            search_y1 = round(y * frame_height)
            search_x2 = round((x + width) * frame_width)
            search_y2 = round((y + height) * frame_height)
        else:
            search_x1 = max(0, round(feature.x * scaling - frame_width * horizontal_variance))
            search_y1 = max(0, round(feature.y * scaling - frame_height * vertical_variance))
            search_x2 = min(frame_width,
                            round((feature.x + feature.width) * scaling + frame_width * horizontal_variance))
            search_y2 = min(frame_height,
                            round((feature.y + feature.height) * scaling + frame_height * vertical_variance))

        search_area = mat[search_y1:search_y2, search_x1:search_x2, :3]
        target_mat = search_area
        if scaling != 1:
            target_mat = cv2.resize(search_area, None, fx=1 / scaling, fy=1 / scaling)

        template = feature.mat
        if use_gray_scale:
            target_mat = cv2.cvtColor(target_mat, cv2.COLOR_BGR2GRAY)
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(target_mat, template, cv2.TM_CCOEFF_NORMED)

        locations = filter_and_sort_matches(result, threshold, feature.width, feature.height)
        boxes = []

        for loc in locations:
            x, y = loc[0] + target_mat.shape[1], loc[1] + target_mat.shape[0]
            confidence = result[loc[1], loc[0]]
            boxes.append(Box(x * scaling, y * scaling, feature.width * scaling, feature.height * scaling, confidence,
                             category_name))

        result = sort_boxes(boxes)
        communicate.emit_draw_box(category_name, result, "red")
        search_name = "search_" + category_name
        communicate.emit_draw_box(search_name,
                                  Box(search_x1, search_y1, to_x=search_x2,
                                      to_y=search_y2,
                                      name=search_name), "blue")
        logger.debug(
            f'find_feature {category_name} scaling {scaling} cost {round((time.time() - start) * 1000)} ms {result}')
        return result


def filter_and_sort_matches(result, threshold, width, height):
    loc = np.where(result >= threshold)
    matches = sorted(zip(*loc[::-1]), key=lambda p: result[p[::-1]], reverse=True)
    unique_matches = []
    for pt in matches:
        if all(not (pt[0] >= m[0] - width and pt[0] <= m[0] + width and pt[1] >= m[1] - height and pt[1] <= m[
            1] + height) for m in unique_matches):
            unique_matches.append(pt)
    return unique_matches
