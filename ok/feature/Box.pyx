import math
import random
import re
from functools import cmp_to_key

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

cdef class Box:
    cdef public int x, y, width, height
    cdef public float confidence
    cdef public object name

    def __init__(self, x, y, width=0, height=0, confidence=1.0, name=None, to_x=-1, to_y=-1):
        self.x = int(round(x))
        self.y = int(round(y))
        if to_x != -1:
            self.width = int(round(to_x - x))
        else:
            self.width = int(round(width))
        if to_y != -1:
            self.height = int(round(to_y - y))
        else:
            self.height = int(round(height))

        if self.width == 0:
            self.width = 1
            logger.warning(f'box width is 0, fixed to 1 {x} {y} {width} {height} {to_x} {to_y}')
        if self.height == 0:
            self.height = 1
            logger.warning(f'box height is 0, fixed to 1 {x} {y} {width} {height} {to_x} {to_y}')

        if self.width <= 0 or self.height <= 0:
            raise ValueError(f'width and height must be greater than zero {x} {y} {width} {height} {to_x} {to_y}')

        self.confidence = confidence
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, Box):
            return NotImplemented
        return (self.x == other.x and self.y == other.y and
                self.width == other.width and self.height == other.height and
                self.confidence == other.confidence and self.name == other.name)

    def area(self) -> int:
        """
        Calculates the area of the box.

        Returns:
            int: The area of the box (width * height).
        """
        # Use cdef types for performance if possible, though for simple multiplication
        # Python integers are often optimized well.
        return self.width * self.height

    def in_boundary(self, boxes):
        cdef list in_boundary_boxes = []
        cdef Box box
        for box in boxes:
            if (self.x <= box.x and self.x + self.width >= box.x + box.width and
                    self.y <= box.y and self.y + self.height >= box.y + box.height):
                in_boundary_boxes.append(box)
        return in_boundary_boxes

    def __repr__(self):
        return f'{self.name}_{self.confidence:.2f}'

    def __str__(self):
        if self.name is not None:
            return f"Box(name='{self.name}', x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"
        return f"Box(x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"

    def scale(self, width_ratio: float, height_ratio: float = None):
        """
        Scales the box by given width and height ratios, keeping the center point the same.
        If the scaling causes x or y to become negative, it will be set to 0,
        while maintaining the center point.

        Args:
            width_ratio: The ratio to scale the width by (e.g., 1.1 for 110%, 0.9 for 90%).
            height_ratio: The ratio to scale the height by (e.g., 1.1 for 110%, 0.9 for 90%).
                          If None, defaults to the width_ratio.

        Returns:
            A new Box object with the scaled dimensions and position.
        """

        if height_ratio is None:
            height_ratio = width_ratio

        center_x = self.x + self.width / 2.0
        center_y = self.y + self.height / 2.0

        new_width = round(self.width * width_ratio)
        new_height = round(self.height * height_ratio)

        new_x = round(center_x - new_width / 2.0)
        new_y = round(center_y - new_height / 2.0)

        if new_x < 0:
            new_x = 0

        if new_y < 0:
            new_y = 0

        return Box(new_x, new_y, new_width, new_height, confidence=self.confidence, name=self.name)

    def closest_distance(self, Box other):
        cdef int horizontal_distance, vertical_distance
        cdef int right1 = self.x + self.width
        cdef int bottom1 = self.y + self.height
        cdef int right2 = other.x + other.width
        cdef int bottom2 = other.y + other.height

        horizontal_distance = max(0, max(self.x, other.x) - min(right1, right2))
        vertical_distance = max(0, max(self.y, other.y) - min(bottom1, bottom2))
        return 0.0 if horizontal_distance == 0 and vertical_distance == 0 else math.sqrt(
            horizontal_distance ** 2 + vertical_distance ** 2)

    cpdef center_distance(self, other):
        x1, y1 = self.center()
        x2, y2 = other.center()

        dx = x2 - x1
        dy = y2 - y1
        # Calculate distance using the distance formula: sqrt((x2-x1)^2 + (y2-y1)^2)
        # Ensure intermediate calculations use float for precision before sqrt
        distance_float = math.sqrt(float(dx ** 2 + dy ** 2))
        # Return the integer part of the distance
        return distance_float

    def relative_with_variance(self, float relative_x=0.5, float relative_y=0.5):
        cdef float center_x = self.x + self.width * relative_x
        cdef float center_y = self.y + self.height * relative_y
        cdef float variance = random.uniform(0, 0.1)
        return int(round(center_x + variance)), int(round(center_y + variance))

    def copy(self, int x_offset=0, int y_offset=0, int width_offset=0, int height_offset=0, name=None):
        return Box(self.x + x_offset, self.y + y_offset, self.width + width_offset, self.height + height_offset,
                   self.confidence, name or self.name)

    def crop_frame(self, frame):  # type is unkown, can not be typed
        return frame[self.y:self.y + self.height, self.x:self.x + self.width]

    def center(self):
        return round(self.x + self.width / 2.0), round(self.y + self.height / 2.0)

    cdef float _distance_criteria(self, Box box, str direction, int orig_x, int orig_y, int orig_w, int orig_h,
                                  condition=None):
        cdef int box_x = box.x, box_y = box.y, box_w = box.width, box_h = box.height
        cdef int dx = max(orig_x - (box_x + box_w), box_x - (orig_x + orig_w), 0)
        cdef int dy = max(orig_y - (box_y + box_h), box_y - (orig_y + orig_h), 0)
        cdef float distance = math.sqrt(dx ** 2 + dy ** 2)
        if box is self:
            return float('inf')

        if direction == 'up' and self.y - (box.y + box.height / 2) >= 0:
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
            return float('inf')

        if condition is not None and not condition(box):
            return float('inf')

        return distance

    def find_closest_box(self, str direction, list boxes, condition=None):
        cdef int orig_x = self.x, orig_y = self.y, orig_w = self.width, orig_h = self.height

        boxes.sort(key=lambda box: self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition))
        for box in boxes:
            if self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition) != float('inf'):
                return box
        return None

cdef bint box_intersect(Box box1, Box box2):  # cdef function, no closure issues
    return not (box1.y > box2.y + box2.height or box1.y + box1.height < box2.y)

cdef int compare_boxes(Box box1, Box box2):  # cdef function, no closure issues
    cdef int cmp
    if box_intersect(box1, box2):
        cmp = box1.x - box2.x
        if cmp == 0:
            cmp = box1.y - box2.y
    else:
        cmp = box1.y - box2.y
        if cmp == 0:
            cmp = box1.x - box2.x
    if cmp == 0:
        cmp = int(box1.confidence * 1000 - box2.confidence * 1000)  #Use int to compare float
    if cmp == 0 and box1.name is not None and box2.name is not None:
        cmp = (box1.name > box2.name) - (box1.name < box2.name)
    return cmp

def find_highest_confidence_box(boxes):
    if not boxes:
        return None
    return max(boxes, key=lambda box: box.confidence)

cpdef sort_boxes(list[Box] boxes):
    boxes.sort(key=cmp_to_key(compare_boxes))  #Use external cdef function
    return boxes

cpdef Box find_box_by_name(list[Box] boxes, object names):
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    cdef Box result = None
    cdef int priority = len(names)
    cdef int i
    cdef name
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

def get_bounding_box(list[Box] boxes):
    if not boxes:
        raise ValueError("The list of boxes is empty")

    cdef int min_x = min(box.x for box in boxes)
    cdef int min_y = min(box.y for box in boxes)
    cdef int max_x = max(box.x + box.width for box in boxes)
    cdef int max_y = max(box.y + box.height for box in boxes)

    return Box(min_x, min_y, max_x - min_x, max_y - min_y)

cpdef list[Box] find_boxes_within_boundary(list[Box] boxes, Box boundary_box, bint sort=True):
    cdef list[Box] within_boundary = []

    for box in boxes:
        if (box.x >= boundary_box.x and
                box.y >= boundary_box.y and
                box.x + box.width <= boundary_box.x + boundary_box.width and
                box.y + box.height <= boundary_box.y + boundary_box.height):
            within_boundary.append(box)
    if sort:
        within_boundary = sort_boxes(within_boundary)
    return within_boundary

def average_width(list[Box] boxes):
    cdef int total_width = sum(box.width for box in boxes)
    return int(total_width / len(boxes)) if boxes else 0

cpdef object crop_image(object image, Box box=None):
    if box is not None:
        if (0 <= box.x <= image.shape[1] - box.width and
                0 <= box.y <= image.shape[0] - box.height and
                box.width > 0 and box.height > 0):
            return image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            return image
    return image

def relative_box(frame_width, frame_height, x, y, to_x=1, to_y=1, width=0, height=0, name=None, confidence=1.0):
    if width == 0:
        width = to_x - x
    if height == 0:
        height = to_y - y
    return Box(round(x * frame_width), round(y * frame_height),
               round(width * frame_width), round(height * frame_height),
               name=name, confidence=confidence)

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
