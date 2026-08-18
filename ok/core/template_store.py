"""Headless storage for template images and COCO annotations."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
EMPTY_COCO = {"images": [], "annotations": [], "categories": []}


def filename_key(value):
    return Path(str(value or "").replace("\\", "/")).name.casefold()


class CocoTemplateStore:
    """Own filesystem and COCO mutations shared by desktop and web UIs."""

    def __init__(self, folder="ok_templates", coco_name="coco_annotations.json"):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.coco_path = self.folder / coco_name
        self._lock = threading.RLock()

    def image_path(self, name):
        safe_name = Path(str(name or "")).name
        if not safe_name or Path(safe_name).suffix.lower() not in TEMPLATE_EXTENSIONS:
            raise ValueError("Invalid template image")
        path = (self.folder / safe_name).resolve()
        if path.parent != self.folder:
            raise ValueError("Invalid template path")
        return path

    def load(self):
        with self._lock:
            if not self.coco_path.is_file():
                return {key: list(value) for key, value in EMPTY_COCO.items()}
            try:
                data = json.loads(self.coco_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {key: list(value) for key, value in EMPTY_COCO.items()}
            return {
                "images": list(data.get("images") or []),
                "annotations": list(data.get("annotations") or []),
                "categories": list(data.get("categories") or []),
            }

    def save(self, data):
        with self._lock:
            normalized = {
                "images": sorted(data.get("images") or [], key=lambda item: int(item.get("id", 0))),
                "annotations": sorted(data.get("annotations") or [], key=lambda item: int(item.get("id", 0))),
                "categories": sorted(data.get("categories") or [], key=lambda item: int(item.get("id", 0))),
            }
            handle, temporary = tempfile.mkstemp(prefix=".coco-", suffix=".json", dir=self.folder)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(normalized, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.coco_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return normalized

    @staticmethod
    def _cleanup_categories(data):
        used = {item.get("category_id") for item in data.get("annotations", [])}
        data["categories"] = [item for item in data.get("categories", []) if item.get("id") in used]

    @staticmethod
    def _next_id(items):
        return max((int(item.get("id", 0)) for item in items), default=0) + 1

    def _dimensions(self, path):
        import cv2
        frame = cv2.imread(str(path))
        if frame is None:
            return 0, 0
        height, width = frame.shape[:2]
        return int(width), int(height)

    def _image_entry(self, data, path):
        key = filename_key(path.name)
        return next((item for item in data["images"] if filename_key(item.get("file_name")) == key), None)

    def ensure_image(self, data, path):
        image = self._image_entry(data, path)
        if image is None:
            width, height = self._dimensions(path)
            image = {
                "id": self._next_id(data["images"]),
                "file_name": path.name,
                "width": width,
                "height": height,
            }
            data["images"].append(image)
        return image

    def list_images(self):
        with self._lock:
            data = self.load()
            categories = {item.get("id"): str(item.get("name", "")) for item in data["categories"]}
            image_ids = {filename_key(item.get("file_name")): item.get("id") for item in data["images"]}
            by_image = {}
            for item in data["annotations"]:
                name = categories.get(item.get("category_id"), "")
                if name and name not in by_image.setdefault(item.get("image_id"), []):
                    by_image[item.get("image_id")].append(name)
            paths = [item for item in self.folder.iterdir() if item.is_file() and item.suffix.lower() in TEMPLATE_EXTENSIONS]
            paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            return [{
                "path": path,
                "modified": path.stat().st_mtime,
                "categories": by_image.get(image_ids.get(filename_key(path.name)), []),
            } for path in paths]

    def annotations_for(self, name):
        with self._lock:
            path = self.image_path(name)
            if not path.is_file():
                raise ValueError("Template not found")
            data = self.load()
            image = self._image_entry(data, path)
            width = int((image or {}).get("width") or 0)
            height = int((image or {}).get("height") or 0)
            if width <= 0 or height <= 0:
                width, height = self._dimensions(path)
            categories = {item.get("id"): item.get("name", "") for item in data["categories"]}
            annotations = [] if image is None else [{
                "id": item.get("id"),
                "category": categories.get(item.get("category_id"), ""),
                "bbox": list(item.get("bbox", [0, 0, 0, 0])),
            } for item in data["annotations"] if item.get("image_id") == image.get("id")]
            return {"path": path, "width": width, "height": height, "annotations": annotations}

    def replace_annotations(self, name, annotations):
        if not isinstance(annotations, list):
            raise ValueError("Invalid annotations")
        with self._lock:
            path = self.image_path(name)
            if not path.is_file():
                raise ValueError("Template not found")
            data = self.load()
            image = self.ensure_image(data, path)
            width = max(0, int(image.get("width") or 0))
            height = max(0, int(image.get("height") or 0))
            data["annotations"] = [item for item in data["annotations"] if item.get("image_id") != image["id"]]
            categories = {str(item.get("name", "")): item for item in data["categories"]}
            next_category = self._next_id(data["categories"])
            next_annotation = self._next_id(data["annotations"])
            for annotation in annotations:
                category_name = str(annotation.get("category", "")).strip()
                bbox = annotation.get("bbox")
                if not category_name or not isinstance(bbox, list) or len(bbox) != 4:
                    raise ValueError("Invalid bounding box")
                try:
                    x, y, box_width, box_height = (float(value) for value in bbox)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Invalid bounding box") from exc
                x = min(max(0.0, x), float(width)) if width else max(0.0, x)
                y = min(max(0.0, y), float(height)) if height else max(0.0, y)
                box_width = max(0.0, box_width)
                box_height = max(0.0, box_height)
                if width:
                    box_width = min(box_width, width - x)
                if height:
                    box_height = min(box_height, height - y)
                category = categories.get(category_name)
                if category is None:
                    category = {"id": next_category, "name": category_name, "supercategory": ""}
                    next_category += 1
                    data["categories"].append(category)
                    categories[category_name] = category
                values = [x, y, box_width, box_height]
                data["annotations"].append({
                    "id": next_annotation,
                    "image_id": image["id"],
                    "category_id": category["id"],
                    "bbox": values,
                    "area": box_width * box_height,
                    "iscrowd": 0,
                })
                next_annotation += 1
            self._cleanup_categories(data)
            self.save(data)
            return self.annotations_for(name)

    def delete_image(self, name):
        with self._lock:
            path = self.image_path(name)
            if not path.is_file():
                raise ValueError("Template not found")
            data = self.load()
            image_ids = {item.get("id") for item in data["images"] if filename_key(item.get("file_name")) == filename_key(path.name)}
            path.unlink()
            data["images"] = [item for item in data["images"] if item.get("id") not in image_ids]
            data["annotations"] = [item for item in data["annotations"] if item.get("image_id") not in image_ids]
            self._cleanup_categories(data)
            self.save(data)
            return path

    def next_image_name(self):
        with self._lock:
            used = {int(path.stem) for path in self.folder.iterdir() if path.stem.isdigit() and path.suffix.lower() in TEMPLATE_EXTENSIONS}
            for image in self.load()["images"]:
                stem = Path(str(image.get("file_name", ""))).stem
                if stem.isdigit():
                    used.add(int(stem))
            index = 0
            while index in used:
                index += 1
            return f"{index}.png"

    def save_frame(self, frame):
        import cv2
        with self._lock:
            path = self.image_path(self.next_image_name())
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError("Failed to save template image")
            data = self.load()
            self.ensure_image(data, path)
            self.save(data)
            return path
