import json
import os
import sys

import cv2
from PIL import Image


def compress_coco(coco_json) -> None:
    coco_folder = os.path.dirname(coco_json)

    image_dict = {}
    with open(coco_json, 'r') as file:
        data = json.load(file)

        image_map = {image['id']: image['file_name'] for image in data['images']}
        category_map = {category['id']: category['name'] for category in data['categories']}

        for annotation in data['annotations']:
            image_id = annotation['image_id']
            category_id = annotation['category_id']
            bbox = annotation['bbox']

            # Load and scale the image
            image_path = str(os.path.join(coco_folder, image_map[image_id]))
            image = cv2.imread(image_path)
            original_height, original_width = image.shape[:2]
            if image is None:
                print(f'Could not read image {image_path}')
                continue
            x, y, w, h = bbox
            # Crop the image to the bounding box
            image = image[round(y):round(y + h), round(x):round(x + w), :3]

            image_features = image_dict.get(image_path, [])
            image_features.append((round(x), round(y), image, original_width, original_height))
            image_dict[image_path] = image_features

        # Loop through the image_dict and write all the image_feature associated with it in a new PNG
        for image_path, features in image_dict.items():
            background = None
            for feature in features:
                x, y, image, original_width, original_height = feature
                # Create a white background
                if not background:
                    background = Image.new('RGBA', (original_width, original_height), (255, 255, 255, 255))
                # Convert the OpenCV image (numpy array) to a PIL image
                image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGBA))
                # Paste the image onto the background
                background.paste(image, (x, y), image)
                # Save the image with compression level 9
            background.save(image_path, 'PNG', optimize=True, compress_level=9)


if __name__ == '__main__':
    json_file = sys.argv[1]
    compress_coco(json_file)
