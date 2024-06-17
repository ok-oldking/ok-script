import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

from ok.feature.FeatureSet import read_from_json


def compress_coco(coco_json, canny_upper, canny_lower) -> None:
    feature_dict, *_ = read_from_json(coco_json, canny_lower=canny_lower, canny_upper=canny_upper)
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

            # Add metadata
            metadata = {
                "ok_compressed": "1"
            }

            # Save the image with metadata
            save_image_with_metadata(background, image_path, metadata)


def save_image_with_metadata(image, image_path, metadata):
    # Convert OpenCV image (numpy array) to PIL Image
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    # Add metadata
    for key, value in metadata.items():
        pil_image.info[key] = value

    # Save the image with metadata
    pil_image.save(image_path, 'PNG', optimize=True)


if __name__ == '__main__':
    json_file = sys.argv[1]
    compress_coco(json_file)
