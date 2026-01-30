import json
import math
import os
import re
import threading

import cv2
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ok.feature.Box import Box, sort_boxes
from ok.feature.Feature import Feature
from ok.gui.Communicate import communicate
from ok.util.file import get_path_relative_to_exe
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

cdef class FeatureSet:
    cdef int width, height
    cdef double default_threshold, default_horizontal_variance, default_vertical_variance
    cdef str coco_json
    cdef bint debug, load_success
    cdef dict feature_dict, box_dict
    cdef object lock, feature_processor
    cdef list hcenter_features, vcenter_features

    def __init__(self, debug, coco_json: str, default_horizontal_variance,
                 default_vertical_variance, default_threshold=0.95, feature_processor=None,
                 hcenter_features: list = None, vcenter_features: list = None) -> None:
        self.coco_json = get_path_relative_to_exe(coco_json)
        self.debug = debug
        self.feature_dict = {}
        self.box_dict = {}
        self.load_success = False
        self.feature_processor = feature_processor
        self.hcenter_features = hcenter_features if hcenter_features is not None else []
        self.vcenter_features = vcenter_features if vcenter_features is not None else []

        logger.debug(f'Loading features from {self.coco_json}')

        self.width = 0
        self.height = 0
        if default_threshold == 0:
            default_threshold = 0.95
        self.default_threshold = default_threshold
        self.default_horizontal_variance = default_horizontal_variance
        self.default_vertical_variance = default_vertical_variance
        self.lock = threading.Lock()

    def feature_exists(self, feature_name: str) -> bool:
        return feature_name in self.feature_dict

    cdef bint empty(self):
        return len(self.feature_dict) == 0 and len(self.box_dict) == 0

    cpdef bint check_size(self, object frame):
        with self.lock:
            height, width = frame.shape[:2]
            if self.width != width or self.height != height and height > 0 and width > 0:
                logger.info(f"FeatureSet: Width and height changed from {self.width}x{self.height} to {width}x{height}")
                self.width = width
                self.height = height
                self.process_data()
            elif not self.feature_dict:
                self.process_data()
        return self.load_success

    cdef bint process_data(self):
        self.feature_dict, self.box_dict, compressed, self.load_success = read_from_json(self.coco_json, self.width,
                                                                                         self.height,
                                                                                         self.hcenter_features,
                                                                                         self.vcenter_features)
        if self.debug and not compressed:
            logger.info(f'coco not compressed try to compress the COCO dataset')
            compress_coco(self.coco_json)
            self.feature_dict, self.box_dict, compressed, self.load_success = read_from_json(self.coco_json, self.width,
                                                                                             self.height,
                                                                                             self.hcenter_features,
                                                                                             self.vcenter_features)
        if self.feature_processor:
            logger.info('process features with feature_processor')
            for feature in self.feature_dict:
                self.feature_processor(feature, self.feature_dict[feature])
        return self.load_success

    cpdef object get_box_by_name(self, mat, category_name):
        self.check_size(mat)
        return self.box_dict.get(category_name)

    cdef save_images(self, str target_folder):
        os.makedirs(target_folder, exist_ok=True)

        for category_name, image in self.feature_dict.items():
            file_name = f"{category_name}.jpg"
            file_path = os.path.join(target_folder, file_name)

            cv2.imwrite(file_path, image.mat)

    cpdef object get_feature_by_name(self, mat, name):
        self.check_size(mat)
        return self.feature_dict.get(name)

    def find_one_feature(self, mat: np.ndarray, category_name, horizontal_variance: float = 0,
                         vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                         to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0, canny_higher=0,
                         frame_processor=None, template=None, mask_function=None, match_method=cv2.TM_CCOEFF_NORMED,
                         screenshot=False):
        self.check_size(mat)

        if threshold == 0:
            threshold = self.default_threshold
        if horizontal_variance == 0:
            horizontal_variance = self.default_horizontal_variance
        if vertical_variance == 0:
            vertical_variance = self.default_vertical_variance
        if template is None and category_name not in self.feature_dict:
            raise ValueError(f"FeatureSet: {category_name} not found in featureDict")
        if template is None:
            feature = self.feature_dict[category_name]
            template = feature.mat
        else:
            feature = None
        if box is not None:
            search_x1 = max(box.x, 0)
            search_y1 = max(box.y, 0)
            search_x2 = min(box.x + box.width, mat.shape[1])
            search_y2 = min(box.y + box.height, mat.shape[0])
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
        elif feature is None:
            search_x1 = 0
            search_y1 = 0
            search_y2, search_x2 = mat.shape[:2]
        else:
            x_offset = self.width * horizontal_variance
            y_offset = self.height * vertical_variance
            if feature.scaling != 1:
                if horizontal_variance == 0:
                    x_offset = 1
                if vertical_variance == 0:
                    y_offset = 1

            search_x1 = max(0, round(feature.x - x_offset))
            search_y1 = max(0, round(feature.y - y_offset))
            feature_width, feature_height = feature.width, feature.height
            search_x2 = min(self.width, round(feature.x + feature_width + x_offset))
            search_y2 = min(self.height, round(feature.y + feature_height + y_offset))

        search_area = mat[search_y1:search_y2, search_x1:search_x2, :3]

        feature_height, feature_width = template.shape[:2]
        if use_gray_scale:
            search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            if len(feature.mat.shape) != 2:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if canny_lower != 0 and canny_higher != 0:
            if len(search_area.shape) != 2:
                search_area = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
            search_area = cv2.Canny(search_area, canny_lower, canny_higher)
            if len(template.shape) != 2:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
                template = cv2.Canny(template, canny_lower, canny_higher)
        if feature is not None and feature.mask is None:
            if mask_function is not None:
                feature.mask = mask_function(feature.mat)
        mask = None
        if feature is not None:
            mask = feature.mask
            feature.mat = template
        elif mask_function is not None:
            mask = mask_function(template)

        if frame_processor is not None:
            search_area = frame_processor(search_area)

        if feature is not None and (
                feature.mat.shape[1] > search_area.shape[1] or feature.mat.shape[0] > search_area.shape[0]):
            logger.error(
                f'feature template {category_name} {box.name if box else ""} size greater than search area {feature.mat.shape} > {search_area.shape}')

        result = cv2.matchTemplate(search_area, template, match_method,
                                   mask=mask)

        if screenshot:
            logger.info(f'template matching screenshot match_method:{match_method} canny:{canny_lower, canny_higher}')
            communicate.screenshot.emit(mat, "mat", True, None)
            communicate.screenshot.emit(search_area, "search_area", False, box)
            communicate.screenshot.emit(template, "template", False, None)

        locations = filter_and_sort_matches(result, threshold, feature_width, feature_height)
        boxes = []

        for loc in locations:
            x, y = loc[0][0] + search_x1, loc[0][1] + search_y1
            confidence = 1.0 if math.isinf(loc[1]) and loc[1] > 0 else loc[1]
            boxes.append(Box(x, y, feature_width, feature_height, confidence, category_name))

        boxes = sort_boxes(boxes)
        if category_name:
            communicate.emit_draw_box(category_name, boxes, "red")
            search_name = "search_" + category_name
            communicate.emit_draw_box(search_name,
                                      Box(search_x1, search_y1, search_x2 - search_x1, search_y2 - search_y1,
                                          name=search_name), "blue")
        return boxes

    def find_feature(self, mat: np.ndarray, category_name, horizontal_variance: float = 0,
                     vertical_variance: float = 0, threshold: float = 0, use_gray_scale: bool = False, x=-1, y=-1,
                     to_x=-1, to_y=-1, width=-1, height=-1, box=None, canny_lower=0, canny_higher=0,
                     frame_processor=None, template=None, mask_function=None, match_method=cv2.TM_CCOEFF_NORMED,
                     screenshot=False):
        if type(category_name) is list:
            results = []
            for cn in category_name:
                results += self.find_one_feature(mat=mat, category_name=cn,
                                                 horizontal_variance=horizontal_variance,
                                                 vertical_variance=vertical_variance, threshold=threshold,
                                                 use_gray_scale=use_gray_scale, x=x, y=y,
                                                 to_x=to_x, to_y=to_y, width=width, height=height, box=box,
                                                 canny_lower=canny_lower, canny_higher=canny_higher,
                                                 frame_processor=frame_processor,
                                                 template=template, mask_function=mask_function,
                                                 match_method=match_method, screenshot=screenshot)
            return sort_boxes(results)
        else:
            return self.find_one_feature(mat=mat, category_name=category_name,
                                         horizontal_variance=horizontal_variance,
                                         vertical_variance=vertical_variance, threshold=threshold,
                                         use_gray_scale=use_gray_scale, x=x, y=y,
                                         to_x=to_x, to_y=to_y, width=width, height=height, box=box,
                                         canny_lower=canny_lower, canny_higher=canny_higher,
                                         frame_processor=frame_processor,
                                         template=template, mask_function=mask_function, match_method=match_method,
                                         screenshot=screenshot)

def read_from_json(coco_json, width=-1, height=-1, hcenter_features=None, vcenter_features=None, adjust=True):
    feature_dict = {}
    box_dict = {}
    ok_compressed = None
    load_success = True
    data = load_json(coco_json)
    coco_folder = os.path.dirname(coco_json)
    logger.info(f"read_from_json {coco_folder} {coco_json}")

    image_map = {image['id']: image['file_name'] for image in data['images']}
    category_map = {category['id']: category['name'] for category in data['categories']}

    for image_id, file_name in image_map.items():
        image_path = str(os.path.join(coco_folder, file_name))
        if ok_compressed is None:
            with Image.open(image_path) as img:
                ok_compressed = 'ok_compressed' in img.info.keys()
        whole_image = cv2.imread(image_path)
        if whole_image is None:
            logger.error(f'Could not read image {image_path}')
            raise ValueError(f'Could not read image {image_path}')
        _, original_width = whole_image.shape[:2]
        image_height, image_width = whole_image.shape[:2]

        for annotation in data['annotations']:
            if image_id != annotation['image_id']:
                continue

            category_id = annotation['category_id']
            bbox = annotation['bbox']
            x, y, w, h = bbox

            image = whole_image[round(y):round(y + h), round(x):round(x + w), :3]

            x, y = round(x), round(y)
            h, w, _ = image.shape

            category_name = category_map[category_id]

            is_hcenter = 'hcenter' in category_name or (hcenter_features and category_name in hcenter_features)
            is_vcenter = 'vcenter' in category_name or (vcenter_features and category_name in vcenter_features)

            if adjust:
                x, y, w, h, scale = adjust_coordinates(x, y, w, h, width, height, image_width, image_height,
                                                       hcenter=is_hcenter, vcenter=is_vcenter)

                image = cv2.resize(image, (w, h))
            else:
                scale = 1

            logger.debug(
                f"loaded {category_name} resized width {width} / original_width:{original_width},scale_x:{width / original_width}")
            if category_name in feature_dict:
                raise ValueError(f"Multiple boxes found for category {category_name}")
            feature_dict[category_name] = Feature(image, x, y, scale)
            box_dict[category_name] = Box(x, y, image.shape[1], image.shape[0], name=category_name)

    return feature_dict, box_dict, ok_compressed, load_success

def load_json(coco_json):
    with open(coco_json, 'r') as file:
        data = json.load(file)
        for images in data['images']:
            images['file_name'] = un_fk_label_studio_path(images['file_name'])
        return data

def un_fk_label_studio_path(path):
    if os.path.isabs(path):
        match = re.search(r'\\(images\\.*\.(jpg|png)$)', path)
        if match:
            return match.group(1).replace("images\\", "images/")
    return path

def adjust_coordinates(x, y, w, h, screen_width, screen_height, image_width, image_height, hcenter=False,
                       vcenter=False):
    # logger.debug(f'scaling images {screen_width}x{screen_height} {image_width}x{image_height} {x}, {y}, {w}, {h}')
    if screen_width != -1 and screen_height != -1 and (screen_width != image_width or screen_height != image_height):
        scale_x, scale_y = screen_width / image_width, screen_height / image_height
    else:
        scale_x, scale_y = 1, 1

    scale = min(scale_x, scale_y)
    w, h = round(w * scale), round(h * scale)

    if scale_x > scale_y:
        y = round(y * scale)
        x = scale_by_anchor(x, image_width, screen_width, scale, hcenter=hcenter)
    elif scale_x < scale_y:
        x = round(x * scale)
        y = scale_by_anchor(y, image_height, screen_height, scale, hcenter=vcenter)
    else:
        x, y = round(x * scale), round(y * scale)

    # logger.debug(f'scaled images {scale_x}, {scale_y} to {screen_width}x{screen_height} {x}, {y}, {w}, {h}')

    return x, y, w, h, scale

def scale_by_anchor(x, image_width, screen_width, scale, hcenter=False):
    if (x + image_width) / 2 > screen_width * 0.5:
        if hcenter:
            x = round(screen_width * 0.5 + (x - image_width * 0.5) * scale)
        else:
            x = screen_width - round((image_width - x) * scale)
    else:
        if hcenter:
            x = round(screen_width * 0.5 - (image_width * 0.5 - x) * scale)
        else:
            x = round(x * scale)
    return x

def replace_extension(filename):
    if filename.endswith('.jpg'):
        return filename[:-4] + '.png', True

def filter_and_sort_matches(result, threshold, w, h):
    loc = np.where(result >= threshold)
    matches = list(zip(*loc[::-1]))

    confidences = result[result >= threshold]

    matches_with_confidence = sorted(zip(matches, confidences), key=lambda x: x[1], reverse=True)

    selected_matches = []

    def is_overlapping(match, selected):
        x1, y1 = match
        for (x2, y2), _ in selected:
            if (x1 < x2 + w and x1 + w > x2 and y1 < y2 + h and y1 + h > y2):
                return True
        return False

    for match, confidence in matches_with_confidence:
        if not is_overlapping(match, selected_matches):
            selected_matches.append((match, confidence))

    return selected_matches

def compress_copy_coco(coco_json, target_folder, image_folder) -> str:
    import shutil
    
    os.makedirs(target_folder, exist_ok=True)
    target_image_folder = os.path.join(target_folder, 'images')
    os.makedirs(target_image_folder, exist_ok=True)
    
    data = load_json(coco_json)
    
    for image_info in data['images']:
        image_filename = os.path.basename(image_info['file_name'])
        
        source_image_path = os.path.join(image_folder, image_filename)
        
        new_relative_path = f"images/{image_filename}"
        
        target_image_path = os.path.join(target_folder, new_relative_path)
        if os.path.exists(source_image_path):
            shutil.copy2(source_image_path, target_image_path)
            logger.info(f'Copied image: {source_image_path} -> {target_image_path}')
        else:
            logger.warning(f'Source image not found: {source_image_path}')
            
        image_info['file_name'] = new_relative_path
    
    for annotation in data['annotations']:
        bbox = annotation['bbox']
        annotation['bbox'] = [round(bbox[0]), round(bbox[1]), round(bbox[2]), round(bbox[3])]
    
    target_coco_json = os.path.join(target_folder, os.path.basename(coco_json))
    with open(target_coco_json, 'w') as json_file:
        json.dump(data, json_file, indent=4)
    
    logger.info(f'Copied COCO JSON to: {target_coco_json}')
    
    compress_coco(target_coco_json)
    
    return target_coco_json

def compress_coco(coco_json) -> None:
    feature_dict, *_ = read_from_json(coco_json, adjust=False)
    image_dict = {}
    data = load_json(coco_json)

    coco_folder = os.path.dirname(coco_json)
    image_map = {image['id']: image['file_name'] for image in data['images']}
    category_map = {category['id']: category['name'] for category in data['categories']}

    for annotation in data['annotations']:
        image_id = annotation['image_id']
        category_id = annotation['category_id']

        feature = feature_dict.get(category_map[category_id])
        if feature:
            image_path = image_map[image_id]
            image_features = image_dict.get(image_path, [])
            image_features.append(feature)
            image_dict[image_path] = image_features

    i = 0
    renamed_path = {}
    for relative_path, features in image_dict.items():
        image_path = str(os.path.join(coco_folder, relative_path))
        background = None
        for feature in features:
            if background is None:
                if not os.path.exists(image_path):
                    raise ValueError(f'{image_path} not exists')
                original_image = cv2.imread(image_path)
                background = np.full_like(original_image,
                                          255)

            x, y = feature.x, feature.y
            h, w = feature.mat.shape[:2]
            background[y:y + h, x:x + w] = feature.mat

        if background is None:
            logger.error(f'no feature in {image_path}')
            raise ValueError(f'no feature in {image_path}')

        new_path_relative = replace_extension(i, relative_path)
        new_path_relative = new_path_relative.replace('\\', '/')
        renamed_path[relative_path] = new_path_relative
        logger.debug(f'renamed_path {relative_path} {new_path_relative}')

        new_path_absolute = replace_extension(i, image_path)
        save_image_with_metadata(background, image_path, new_path_absolute)
        i += 1

    for image in data['images']:
        if renamed := renamed_path.get(image['file_name']):
            image['file_name'] = renamed
        else:
            raise ValueError(f'{image["file_name"]} does not contain any annotation')

    with open(coco_json, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def replace_extension(i, file_name):
    folder_name = os.path.dirname(file_name)
    new_base_name = f'{i}.png'
    return os.path.join(folder_name, new_base_name)

def save_image_with_metadata(image, image_path, new_path):
    try:
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        metadata = PngInfo()

        metadata.add_text('ok_compressed', '1')
        metadata.add_text("Author", "ok_compress")
        metadata.add_text("Description", "This is a sample image")

        if os.path.normpath(image_path) != os.path.normpath(new_path):
            os.remove(image_path)
        pil_image.save(new_path, 'PNG', optimize=True, pnginfo=metadata)
        return image_path
    except Exception as e:
        logger.error(f'save_image_with_metadata error {image} {image_path}', e)
        raise e