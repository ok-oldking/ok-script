import json
import math
import os
import threading
from typing import Dict
from typing import List

import cv2
import numpy as np
from PIL import Image

from ok.color.Color import rgb_to_gray
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

    def __init__(self, debug, coco_json: str, default_horizontal_variance=0,
                 default_vertical_variance=0, default_threshold=0.95) -> None:
        """
        Initialize the FeatureSet by loading images and annotations from a COCO dataset.

        Args:
            coco_json (str): Directory containing the JSON file and images.
            width (int): Scale images to this width.
            height (int): Scale images to this height.
        """
        self.coco_json = resource_path(coco_json)
        self.debug = debug

        logger.debug(f'Loading features from {self.coco_json}')

        # Process images and annotations
        self.width = 0
        self.height = 0
        if default_threshold == 0:
            default_threshold = 0.95
        self.default_threshold = default_threshold
        self.default_horizontal_variance = default_horizontal_variance
        self.default_vertical_variance = default_vertical_variance
        self.lock = threading.Lock()

    def check_size(self, frame):
        with self.lock:
            height, width = frame.shape[:2]
            if self.width != width or self.height != height and height > 0 and width > 0:
                logger.info(f"FeatureSet: Width and height changed from {self.width}x{self.height} to {width}x{height}")
                self.width = width
                self.height = height
                self.process_data()
            elif not self.feature_dict:
                self.process_data()

    def process_data(self) -> None:
        """
        Process the images and annotations from the COCO dataset.

        Args:
            width (int): Target width for scaling images.
            height (int): Target height for scaling images.
        """
        self.feature_dict, self.box_dict, compressed = read_from_json(self.coco_json, self.width, self.height)
        if self.debug and not compressed:
            from ok.feature.CompressCoco import compress_coco
            logger.info(f'coco not compressed try to compress the COCO dataset')
            compress_coco(self.coco_json)
            self.feature_dict, self.box_dict, compressed = read_from_json(self.coco_json, self.width, self.height)

    def get_box_by_name(self, mat, category_name: str) -> Box:
        self.check_size(mat)
        if category_name in self.box_dict:
            return self.box_dict[category_name]
        else:
            raise ValueError(f"No box found for category {category_name}")

    def save_images(self, target_folder: str) -> None:
        """
        Save all images in the featureDict to the specified folder.

        Args:
            target_folder (str): The folder where images will be saved.
        """
        # Ensure the target folder exists
        os.makedirs(target_folder, exist_ok=True)

        # Iterate through the featureDict and save each image
        for category_name, image in self.feature_dict.items():
            # Construct the filename
            file_name = f"{category_name}.jpg"
            file_path = os.path.join(target_folder, file_name)

            # Save the image
            cv2.imwrite(file_path, image.mat)

    # def find_one(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
    #              vertical_variance: float = 0,
    #              threshold=0, use_gray_scale=False, canny_lower=0, canny_higher=0) -> Box:
    #     boxes = self.find_feature(mat, category_name, horizontal_variance=horizontal_variance,
    #                               vertical_variance=vertical_variance, threshold=threshold,
    #                               use_gray_scale=use_gray_scale, canny_lower=canny_lower, canny_higher=canny_higher)
    #     if len(boxes) > 1:
    #         logger.warning(f"find_one:found too many {len(boxes)} return first", file=sys.stderr)
    #     if len(boxes) >= 1:
    #         return boxes[0]

    def get_feature_by_name(self, name):
        return self.feature_dict.get(name)

    def find_feature(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                     to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0, canny_higher=0,
                     inverse_mask_color=None, frame_processor=None) -> List[Box]:
        """
        Find a feature within a given variance.

        Args:
            mat (np.ndarray): The image in which to find the feature.
            category_name (str): The category name of the feature to find.
            horizontal_variance (float): Allowed horizontal variance as a percentage of width.
            vertical_variance (float): Allowed vertical variance as a percentage of height.
            threshold (float): Allowed confidence threshold for the feature.
            use_gray_scale (bool): If True, convert image to grayscale before finding the feature.

        Returns:
            List[Box]: A list of boxes where the feature is found.
        """
        self.check_size(mat)

        if threshold == 0:
            threshold = self.default_threshold
        if horizontal_variance == 0:
            horizontal_variance = self.default_horizontal_variance
        if vertical_variance == 0:
            vertical_variance = self.default_vertical_variance
        if category_name not in self.feature_dict:
            raise ValueError(f"FeatureSet: " + category_name + " not found in featureDict")
        feature = self.feature_dict[category_name]
        feature_width, feature_height = feature.width, feature.height
        if box is not None:
            search_x1 = box.x
            search_y1 = box.y
            search_x2 = box.x + box.width
            search_y2 = box.y + box.height
        elif x != -1 and y != -1:
            frame_height, frame_width, *_ = mat.shape
            if width == -1:
                width = to_x - x
            if height == -1:
                height = to_y - y
            search_x1 = round(x * frame_width)
            search_y1 = round(y * frame_height)
            search_x2 = round((x + width) * frame_width)
            search_y2 = round((y + height) * frame_height)
        else:
            # Define search area using variance
            x_offset = self.width * horizontal_variance
            y_offset = self.height * vertical_variance
            # if the feature was scaled increase the search area by 1px each direction
            if feature.scaling != 1:
                if horizontal_variance == 0:
                    x_offset = 1
                if vertical_variance == 0:
                    y_offset = 1

            search_x1 = max(0, round(feature.x - x_offset))
            search_y1 = max(0, round(feature.y - y_offset))
            search_x2 = min(self.width, round(feature.x + feature_width + x_offset))
            search_y2 = min(self.height, round(feature.y + feature_height + y_offset))

        search_area = mat[search_y1:search_y2, search_x1:search_x2, :3]

        # Crop the search area from the image

        if use_gray_scale:
            search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            if len(feature.mat.shape) != 2:
                feature.mat = cv2.cvtColor(feature.mat, cv2.COLOR_BGR2GRAY)
        if canny_lower != 0 and canny_higher != 0:
            search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            search_area = cv2.Canny(search_area, canny_lower, canny_higher)
            if len(feature.mat.shape) != 2:
                feature.mat = cv2.cvtColor(feature.mat, cv2.COLOR_BGR2GRAY)
                feature.mat = cv2.Canny(feature.mat, canny_lower, canny_higher)
        if feature.mask is None and inverse_mask_color is not None:
            if len(feature.mat.shape) == 2:
                gray_mask_color = rgb_to_gray(inverse_mask_color)
                feature.mask = cv2.compare(feature.mat, gray_mask_color, cv2.CMP_NE)
            else:
                bound = np.array([inverse_mask_color[0], inverse_mask_color[1], inverse_mask_color[2]],
                                 dtype=np.uint8)
                feature.mask = cv2.inRange(feature.mat, bound, bound)
                feature.mask = cv2.bitwise_not(feature.mask)

        if frame_processor is not None:
            search_area = frame_processor(search_area)

        result = cv2.matchTemplate(search_area, feature.mat, cv2.TM_CCOEFF_NORMED, mask=feature.mask)

        # Define a threshold for acceptable matches
        locations = filter_and_sort_matches(result, threshold, feature_width, feature_height)
        boxes = []

        for loc in locations:  # Iterate through found locations            
            x, y = loc[0][0] + search_x1, loc[0][1] + search_y1
            confidence = 1.0 if math.isinf(loc[1]) and loc[1] > 0 else loc[1]
            boxes.append(Box(x, y, feature_width, feature_height, confidence, category_name))

        boxes = sort_boxes(boxes)
        communicate.emit_draw_box(category_name, boxes, "red")
        search_name = "search_" + category_name
        communicate.emit_draw_box(search_name,
                                  Box(search_x1, search_y1, search_x2 - search_x1, search_y2 - search_y1,
                                      name=search_name), "blue")
        return boxes


def read_from_json(coco_json, width=-1, height=-1):
    feature_dict = {}
    box_dict = {}
    ok_compressed = None
    with open(coco_json, 'r') as file:
        data = json.load(file)
    coco_folder = os.path.dirname(coco_json)

    # Create a map from image ID to file name
    image_map = {image['id']: image['file_name'] for image in data['images']}

    # Create a map from category ID to category name
    category_map = {category['id']: category['name'] for category in data['categories']}

    for image_id, file_name in image_map.items():
        # Load and scale the image
        image_path = str(os.path.join(coco_folder, file_name))
        if ok_compressed is None:
            image = Image.open(image_path)
            ok_compressed = 'ok_compressed' in image.info.keys()
        whole_image = cv2.imread(image_path)
        if whole_image is None:
            logger.error(f'Could not read image {image_path}')
            continue
        _, original_width = whole_image.shape[:2]

        if width != -1 and height != -1 and (width != whole_image.shape[1] or height != whole_image.shape[0]):
            scale_x, scale_y = width / whole_image.shape[1], height / whole_image.shape[0]
            logger.debug(f'scaling images {scale_x}, {scale_y} to {width}x{height}')
        else:
            scale_x, scale_y = 1, 1

        for annotation in data['annotations']:
            if image_id != annotation['image_id']:
                continue

            category_id = annotation['category_id']
            bbox = annotation['bbox']
            x, y, w, h = bbox

            # Crop the image to the bounding box
            image = whole_image[round(y):round(y + h), round(x):round(x + w), :3]

            x, y = round(x), round(y)
            h, w, *_ = image.shape
            # Calculate the scaled bounding box
            x, y, w, h = round(x * scale_x), round(y * scale_y), round(w * scale_x), round(h * scale_y)

            image = cv2.resize(image, (w, h))

            # Store in featureDict using the category name
            category_name = category_map[category_id]
            logger.debug(
                f"loaded {category_name} resized width {width} / original_width:{original_width},scale_x:{width / original_width}")
            if category_name in feature_dict:
                raise ValueError(f"Multiple boxes found for category {category_name}")
            if not category_name.startswith('box_'):
                feature_dict[category_name] = Feature(image, x, y, scale_x)
            box_dict[category_name] = Box(x, y, image.shape[1], image.shape[0], name=category_name)

    return feature_dict, box_dict, ok_compressed


def replace_extension(filename):
    if filename.endswith('.jpg'):
        return filename[:-4] + '.png', True


def filter_and_sort_matches(result, threshold, w, h):
    # Find all matches above the confidence threshold
    loc = np.where(result >= threshold)
    matches = list(zip(*loc[::-1]))  # Convert to (x, y) coordinates

    # Get the match confidence scores
    confidences = result[result >= threshold]

    # Combine the coordinates and confidences, and sort by confidence in descending order
    matches_with_confidence = sorted(zip(matches, confidences), key=lambda x: x[1], reverse=True)

    # List to store selected matches
    selected_matches = []

    def is_overlapping(match, selected):
        x1, y1 = match
        for (x2, y2), _ in selected:
            if (x1 < x2 + w and x1 + w > x2 and y1 < y2 + h and y1 + h > y2):
                return True
        return False

    # Select non-overlapping matches
    for match, confidence in matches_with_confidence:
        if not is_overlapping(match, selected_matches):
            selected_matches.append((match, confidence))

    return selected_matches
