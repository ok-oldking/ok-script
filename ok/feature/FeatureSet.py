import json
import os
import sys
import threading
from typing import Dict
from typing import List

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
        self.coco_folder = os.path.dirname(self.coco_json)
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
        if self.debug:
            folder_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                              for dirpath, dirnames, filenames in os.walk(self.coco_folder)
                              for filename in filenames)
            # Convert size to MB
            folder_size_mb = folder_size / (1024 * 1024)
            if folder_size_mb > 5:
                from ok.feature.CompressCoco import compress_coco
                logger.info(f'template folder greater than 5MB try to compress the COCO dataset')
                compress_coco(self.coco_json)
        self.feature_dict.clear()
        self.box_dict.clear()
        with open(self.coco_json, 'r') as file:
            data = json.load(file)

        # Create a map from image ID to file name
        image_map = {image['id']: image['file_name'] for image in data['images']}

        # Create a map from category ID to category name
        category_map = {category['id']: category['name'] for category in data['categories']}

        for annotation in data['annotations']:
            image_id = annotation['image_id']
            category_id = annotation['category_id']
            bbox = annotation['bbox']

            # Load and scale the image
            image_path = str(os.path.join(self.coco_folder, image_map[image_id]))
            image = cv2.imread(image_path)
            _, original_width = image.shape[:2]
            if image is None:
                logger.error(f'Could not read image {image_path}')
                continue
            x, y, w, h = bbox
            if self.width != image.shape[1] or self.height != image.shape[0]:
                scale_x, scale_y = self.width / image.shape[1], self.height / image.shape[0]
                logger.debug(f'scaling images {scale_x}, {scale_y}')
                image = cv2.resize(image, (self.width, self.height))
                # Calculate the scaled bounding box
                x, y, w, h = x * scale_x, y * scale_y, w * scale_x, h * scale_y

            # Crop the image to the bounding box
            image = image[round(y):round(y + h), round(x):round(x + w), :3]

            # Store in featureDict using the category name
            category_name = category_map[category_id]
            logger.debug(
                f"loaded {category_name} resized width {self.width} / original_width:{original_width},scale_x:{self.width / original_width}")
            if category_name in self.feature_dict:
                raise ValueError(f"Multiple boxes found for category {category_name}")
            if not category_name.startswith('box_'):
                self.feature_dict[category_name] = Feature(image, x, y, w, h)
            self.box_dict[category_name] = Box(x, y, w, h, name=category_name)

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

    def find_one(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
                 vertical_variance: float = 0,
                 threshold=0, use_gray_scale=False) -> Box:
        boxes = self.find_feature(mat, category_name, horizontal_variance=horizontal_variance,
                                  vertical_variance=vertical_variance, threshold=threshold,
                                  use_gray_scale=use_gray_scale)
        if len(boxes) > 1:
            logger.warning(f"find_one:found too many {len(boxes)} return first", file=sys.stderr)
        if len(boxes) >= 1:
            return boxes[0]

    def find_feature(self, mat: np.ndarray, category_name: str, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                     to_x=-1, to_y=-1, width=-1, height=-1, box=None) -> List[Box]:
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
            search_x1 = max(0, round(feature.x - self.width * horizontal_variance))
            search_y1 = max(0, round(feature.y - self.height * vertical_variance))
            search_x2 = min(self.width, round(feature.x + feature_width + self.width * horizontal_variance))
            search_y2 = min(self.height, round(feature.y + feature_height + self.height * vertical_variance))

        search_area = mat[search_y1:search_y2, search_x1:search_x2, :3]
        # Crop the search area from the image
        template = feature.mat
        if use_gray_scale:
            search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)

        # Define a threshold for acceptable matches
        locations = filter_and_sort_matches(result, threshold, feature_width, feature_height)
        boxes = []

        for loc in locations:  # Iterate through found locations            
            x, y = loc[0] + search_x1, loc[1] + search_y1
            confidence = result[loc[1], loc[0]]  # Retrieve the confidence score
            boxes.append(Box(x, y, feature_width, feature_height, confidence, category_name))

        result = sort_boxes(boxes)
        communicate.emit_draw_box(category_name, result, "red")
        search_name = "search_" + category_name
        communicate.emit_draw_box(search_name,
                                  Box(search_x1, search_y1, search_x2 - search_x1, search_y2 - search_y1,
                                      name=search_name), "blue")
        return result


def filter_and_sort_matches(result, threshold, width, height):
    # Filter matches based on the threshold
    loc = np.where(result >= threshold)

    # Zip the locations into a list of tuples and sort by threshold in descending order
    matches = sorted(zip(*loc[::-1]), key=lambda p: result[p[::-1]], reverse=True)

    # Filter out overlapping matches
    unique_matches = []
    for pt in matches:
        if all(not (pt[0] >= m[0] - width and pt[0] <= m[0] + width and
                    pt[1] >= m[1] - height and pt[1] <= m[1] + height)
               for m in unique_matches):
            unique_matches.append(pt)

    # print(f"result {len(result)} loc {len(loc)} matches {len(matches)} unique_matches {unique_matches}")
    return unique_matches
