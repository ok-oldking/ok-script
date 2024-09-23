import os
import cv2
from pathlib import Path


def load_images_from_folder(folder):
    img_map = {}
    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                file_path = Path(root) / file
                img_name = str(file_path.stem)
                if root != folder:
                    img_name = str(Path(root).relative_to(folder)) + '/' + img_name
                img = cv2.imread(str(file_path))
                if img is not None:
                    img_map[img_name] = img
    return img_map


folder_path = r'../docs'
image_map = load_images_from_folder(folder_path)

for key in image_map.keys():
    print(key)
