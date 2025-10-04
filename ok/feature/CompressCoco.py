import json
import os

import cv2
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ok import Logger
from ok import read_from_json, load_json

logger = Logger.get_logger(__name__)


def compress_coco(coco_json) -> None:
    feature_dict, *_ = read_from_json(coco_json)
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
            # Load and scale the image
            image_path = image_map[image_id]
            image_features = image_dict.get(image_path, [])
            image_features.append(feature)
            image_dict[image_path] = image_features

    # Loop through the image_dict and write all the image_feature associated with it in a new PNG
    i = 0
    renamed_path = {}
    for relative_path, features in image_dict.items():
        image_path = str(os.path.join(coco_folder, relative_path))
        background = None
        for feature in features:
            # Create a white background
            if background is None:
                if not os.path.exists(image_path):
                    raise ValueError(f'{image_path} not exists')
                original_image = cv2.imread(image_path)
                background = np.full_like(original_image,
                                          255)  # Create white background with the same shape as original_image

            # Paste the feature onto the background
            x, y = feature.x, feature.y
            h, w = feature.mat.shape[:2]
            background[y:y + h, x:x + w] = feature.mat

        # Save the image with metadata
        if background is None:
            logger.error(f'no feature in {image_path}')
            raise ValueError(f'no feature in {image_path}')
            # Save the image with metadata

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
        # Convert OpenCV image (numpy array) to PIL Image
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        metadata = PngInfo()

        # Add metadata
        metadata.add_text('ok_compressed', '1')
        metadata.add_text("Author", "ok_compress")
        metadata.add_text("Description", "This is a sample image")

        if os.path.normpath(image_path) != os.path.normpath(new_path):
            os.remove(image_path)
        # Save the image with metadata
        pil_image.save(new_path, 'PNG', optimize=True, pnginfo=metadata)
        return image_path
    except Exception as e:
        logger.error(f'save_image_with_metadata error {image} {image_path}', e)
        raise e
