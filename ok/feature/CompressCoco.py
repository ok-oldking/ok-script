import json
import os

import cv2
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ok.feature.FeatureSet import read_from_json
from ok.logging.Logger import get_logger

logger = get_logger(__name__)
def compress_coco(coco_json) -> None:
    feature_dict, *_ = read_from_json(coco_json)
    with open(coco_json, 'r') as file:
        image_dict = {}
        data = json.load(file)
        coco_folder = os.path.dirname(coco_json)
        image_map = {image['id']: image['file_name'] for image in data['images']}
        category_map = {category['id']: category['name'] for category in data['categories']}

        for annotation in data['annotations']:
            image_id = annotation['image_id']
            category_id = annotation['category_id']

            feature = feature_dict.get(category_map[category_id])
            if feature:
                # Load and scale the image
                image_path = str(os.path.join(coco_folder, image_map[image_id]))
                image_features = image_dict.get(image_path, [])
                image_features.append(feature)
                image_dict[image_path] = image_features

        # Loop through the image_dict and write all the image_feature associated with it in a new PNG
        for image_path, features in image_dict.items():
            background = None
            for feature in features:
                # Create a white background
                if background is None:
                    original_image = cv2.imread(image_path)
                    background = np.full_like(original_image,
                                              255)  # Create white background with the same shape as original_image

                # Paste the feature onto the background
                x, y = feature.x, feature.y
                h, w = feature.mat.shape[:2]
                background[y:y + h, x:x + w] = feature.mat

            # Save the image with metadata
            save_image_with_metadata(background, image_path)

        replaced = False
        for image in data['images']:
            image['file_name'], replaced = replace_extension(image['file_name'])

        if replaced:
            with open(coco_json, 'w') as json_file:
                json.dump(data, json_file, indent=4)


def compress_labelme(lableme_json_path) -> None:
    for root, dirs, files in os.walk(lableme_json_path):
        for file in files:
            if not file.endswith('.json'):
                continue
            logger.info(f"load lableme images {file}")
            json_file = str(os.path.join(root, file))
            with open(json_file, 'r') as file:
                data = json.load(file)
            # coco_folder = os.path.dirname(coco_json)

            if 'imagePath' not in data:
                continue
            file_name = data['imagePath']
            image_path = str(os.path.join(root, file_name))
            whole_image = cv2.imread(image_path)
            if whole_image is None:
                load_success = False
                logger.error(f'Could not read image {image_path}')
                continue
            background = None
            for shape in data['shapes']:
                if shape['shape_type'] == "rectangle":
                    points = shape["points"]
                    x, y = points[0]
                    x1, y1 = points[1]
                    x, y = round(x), round(y)
                    x1, y1 = round(x1), round(y1)
                    w, h = x1 - x, y1 - y
                    # Crop the image to the bounding box
                    image = whole_image[round(y):round(y + h), round(x):round(x + w), :3]
                    # h, w, _ = image.shape
                    # Create a white background
                    if background is None:
                        original_image = cv2.imread(image_path)
                        background = np.full_like(original_image,
                                                  255)  # Create white background with the same shape as original_image
                    # Paste the feature onto the background
                    background[y:y + h, x:x + w] = image

            # Save the image with metadata
            save_image_with_metadata(background, image_path)

            data['imagePath'], replaced = replace_extension(file_name)

            if replaced:
                with open(json_file, 'w') as json_file:
                    json.dump(data, json_file, indent=4)



def replace_extension(filename):
    if filename.endswith('.jpg'):
        return filename[:-4] + '.png', True
    return filename, False

def save_image_with_metadata(image, image_path):
    # Convert OpenCV image (numpy array) to PIL Image
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    metadata = PngInfo()

    # Add metadata
    metadata.add_text('ok_compressed', '1')
    metadata.add_text("Author", "ok_compress")
    metadata.add_text("Description", "This is a sample image")
    new_path, replaced = replace_extension(image_path)
    if replaced:
        os.remove(image_path)
    # Save the image with metadata
    pil_image.save(new_path, 'PNG', optimize=True, pnginfo=metadata)
    return image_path
