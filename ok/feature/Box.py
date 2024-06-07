import math
import random
import re
from functools import cmp_to_key
from typing import List


class Box:
    def __init__(self, x: int | float, y: int | float, width: int | float = 0, height: int | float = 0,
                 confidence: float = 1,
                 name=None, to_x: int | float = -1, to_y: int | float = -1) -> None:
        self.name = name
        self.x = int(x)
        self.y = int(y)
        if to_x != -1 and to_y != -1:
            self.width = int(to_x - x)
            self.height = int(to_y - y)
        else:
            self.width = int(width)
            self.height = int(height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f'width and height must be greater than zero {x} {y} {width} {height} {to_x} {to_y}')
        self.confidence = confidence

    def __eq__(self, other):
        if not isinstance(other, Box):
            # Don't attempt to compare against unrelated types
            return NotImplemented

        return (self.x == other.x and
                self.y == other.y and
                self.width == other.width and
                self.height == other.height and
                self.confidence == other.confidence and
                self.name == other.name)

    def in_boundary(self, boxes):
        in_boundary_boxes = []
        for box in boxes:
            if (self.x <= box.x and self.x + self.width >= box.x + box.width and
                    self.y <= box.y and self.y + self.height >= box.y + box.height):
                in_boundary_boxes.append(box)
        return in_boundary_boxes

    def __repr__(self):
        return str(self.name)

    def __str__(self) -> str:
        if self.name is not None:
            return f"Box(name='{self.name}', x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"
        return f"Box(x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"

    def closest_distance(self, other):
        # Calculate the sides of the boxes
        left1, right1 = self.x, self.x + self.width
        top1, bottom1 = self.y, self.y + self.height
        left2, right2 = other.x, other.x + other.width
        top2, bottom2 = other.y, other.y + other.height

        # Horizontal distance
        if right1 < left2:
            horizontal_distance = left2 - right1
        elif right2 < left1:
            horizontal_distance = left1 - right2
        else:
            horizontal_distance = 0

        # Vertical distance
        if bottom1 < top2:
            vertical_distance = top2 - bottom1
        elif bottom2 < top1:
            vertical_distance = top1 - bottom2
        else:
            vertical_distance = 0

        # If boxes overlap or touch, the closest distance is 0
        if horizontal_distance == 0 and vertical_distance == 0:
            return 0

        # If boxes are diagonally aligned, calculate diagonal distance
        return math.sqrt(horizontal_distance ** 2 + vertical_distance ** 2)

    def relative_with_variance(self, relative_x=0.5, relative_y=0.5):
        # Calculate the center of the box
        center_x = self.x + self.width * relative_x
        center_y = self.y + self.height * relative_y

        # Add random variance
        variance = random.uniform(0, 0.1)
        center_x_with_variance = center_x + variance
        center_y_with_variance = center_y + variance
        return round(center_x_with_variance), round(center_y_with_variance)

    def copy(self, x_offset=0, y_offset=0, width_offset=0, height_offset=0, name=None):
        return Box(self.x + x_offset, self.y + y_offset, self.width + width_offset, self.height + height_offset,
                   self.confidence, name or self.name)

    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2

    def find_closest_box(self, direction: str, boxes: list, condition=None):
        orig_x, orig_y, orig_w, orig_h = self.x, self.y, self.width, self.height

        def distance_criteria(box):
            box_x, box_y, box_w, box_h = box.x, box.y, box.width, box.height

            dx = max(orig_x - (box_x + box_w), box_x - (orig_x + orig_w), 0)
            dy = max(orig_y - (box_y + box_h), box_y - (orig_y + orig_h), 0)

            distance = math.sqrt(dx ** 2 + dy ** 2)
            if box == self:
                distance = float('inf')
            elif direction == 'up' and self.y - (box.y + box.height / 2) >= 0:
                pass
            elif direction == 'down' and box.y - (self.y + self.height / 2) >= 0:
                pass
            elif direction == 'left' and self.x - (box.x + box.width / 2) >= 0:
                pass
            elif direction == 'right' and box.x - (self.x + self.width / 2) >= 0:
                pass
            elif direction == 'all':
                pass
            else:
                distance = float('inf')
            return check_condition(box, distance)

        def check_condition(box, distance):
            if condition is None or condition(box):
                return distance
            else:
                return float('inf')

        filtered_boxes = sorted(boxes, key=distance_criteria)

        for box in filtered_boxes:
            if distance_criteria(box) != float('inf'):
                return box
        return None


def sort_boxes(boxes: List[Box]) -> List[Box]:
    def box_intersect(box1, box2):
        return not (box1.y > box2.y + box2.height or box1.y + box1.height < box2.y)

    def compare_boxes(box1, box2):
        if box_intersect(box1, box2):
            cmp = box1.x - box2.x
            if cmp == 0:
                cmp = box1.y - box2.y
        else:
            cmp = box1.y - box2.y
            if cmp == 0:
                cmp = box1.x - box2.y
        if cmp == 0:
            cmp = box1.confidence - box2.confidence
        if cmp == 0:
            cmp = box1.name - box2.name

        return cmp

    return sorted(boxes, key=cmp_to_key(compare_boxes))


def find_box_by_name(boxes, names) -> Box:
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = None
    priority = len(names)

    for box in boxes:
        for i, name in enumerate(names):
            if (isinstance(name, str) and name == box.name) or (
                    isinstance(name, re.Pattern) and re.search(name, box.name)):
                if i < priority:
                    priority = i
                    result = box
                    if i == 0:
                        break

    return result


def find_boxes_within_boundary(boxes, boundary_box):
    """
    Find all boxes that are entirely within the specified boundary box.

    Parameters:
    - boxes (list[Box]): List of Box objects to check.
    - boundary_box (Box): The boundary Box object.

    Returns:
    - list[Box]: Boxes found within the boundary box.
    """
    within_boundary = []

    for box in boxes:
        # Check if box is within boundary_box
        if (box.x >= boundary_box.x and
                box.y >= boundary_box.y and
                box.x + box.width <= boundary_box.x + boundary_box.width and
                box.y + box.height <= boundary_box.y + boundary_box.height):
            within_boundary.append(box)

    return within_boundary


def average_width(boxes: List[Box]) -> int:
    total_width = sum(box.width for box in boxes)
    return int(total_width / len(boxes)) if boxes else 0


def crop_image(image, box=None):
    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
                box.x + box.width <= image.shape[1] and  # image.shape[1] is the width of the image
                box.y + box.height <= image.shape[0]):  # image.shape[0] is the height of the image

            # Extract the region of interest (ROI) using slicing

            return image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            # Return some error value or raise an exception
            # For example, return 0 or None
            return image  # or None, or raise an exception
    else:
        return image


def find_boxes_by_name(boxes, names) -> list[Box]:
    # Ensure names is always a list
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = []

    for box in boxes:
        # Flag to track if the box has been matched and should be added
        matched = False
        for name in names:
            if matched:
                break  # Stop checking names if we've already matched this box
            if (isinstance(name, str) and name == box.name) or (isinstance(box.name, str) and
                                                                isinstance(name, re.Pattern) and re.search(name,
                                                                                                           box.name)):
                matched = True
        if matched:
            result.append(box)

    return result


def boxes_to_map_by_list_of_names(boxes: list[Box], name_list: list[str]) -> dict[str, Box]:
    box_dict = {}
    if boxes:
        for box in boxes:
            if box.name in name_list:
                box_dict[box.name] = box
        if len(box_dict) == len(name_list):
            return box_dict


def relative_box(frame_width, frame_height, x, y, to_x=1, to_y=1, width=0, height=0, name=None):
    if width == 0:
        width = to_x - x
    if height == 0:
        height = to_y - y
    return Box(int(x * frame_width), int(y * frame_height),
               int(width * frame_width), int(height * frame_height),
               name=name)
