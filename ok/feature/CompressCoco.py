import json
import os

import cv2
import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ok.feature.FeatureSet import read_from_json


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


def replace_extension(filename):
    if filename.endswith('.jpg'):
        return filename[:-4] + '.png', True


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
