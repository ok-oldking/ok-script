import math
import random
import re
from functools import cmp_to_key

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)


class Box:
    """
    A class representing a bounding box with coordinates, dimensions, confidence, and name.

    表示边界框的类，包含坐标、尺寸、置信度和名称。
    """

    def __init__(self, x, y, width=0, height=0, confidence=1.0, name=None, to_x=-1, to_y=-1):
        """
        Initializes a Box instance.

        初始化 Box 实例。

        :param x: The x-coordinate of the top-left corner. 左上角的 x 坐标。
        :param y: The y-coordinate of the top-left corner. 左上角的 y 坐标。
        :param width: The width of the box (alternative to to_x). 框的宽度（to_x 的替代）。
        :param height: The height of the box (alternative to to_y). 框的高度（to_y 的替代）。
        :param confidence: The confidence score of the detection. 检测的置信度分数。
        :param name: Optional name or label for the box. 可选的框名称或标签。
        :param to_x: The x-coordinate of the bottom-right corner (alternative to width). 右下角的 x 坐标（width 的替代）。
        :param to_y: The y-coordinate of the bottom-right corner (alternative to height). 右下角的 y 坐标（height 的替代）。
        """
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
        """
        Checks if two Box instances are equal.

        检查两个 Box 实例是否相等。

        :param other: The other Box instance to compare. 要比较的另一个 Box 实例。
        :return: True if equal, False otherwise. 如果相等返回 True，否则返回 False。
        """
        if not isinstance(other, Box):
            return NotImplemented
        return (self.x == other.x and self.y == other.y and
                self.width == other.width and self.height == other.height and
                self.confidence == other.confidence and self.name == other.name)

    def area(self) -> int:
        """
        Calculates the area of the box.

        计算框的面积。

        :return: The area (width * height). 面积（宽度 * 高度）。
        """
        return self.width * self.height

    def in_boundary(self, boxes):
        """
        Finds boxes that are completely within this box's boundary.

        查找完全在此框边界内的框。

        :param boxes: List of boxes to check. 要检查的框列表。
        :return: List of boxes within the boundary. 在边界内的框列表。
        """
        in_boundary_boxes = []
        for box in boxes:
            if (self.x <= box.x and self.x + self.width >= box.x + box.width and
                    self.y <= box.y and self.y + self.height >= box.y + box.height):
                in_boundary_boxes.append(box)
        return in_boundary_boxes

    def __repr__(self):
        """
        Returns a string representation of the Box for debugging.

        返回 Box 的字符串表示，用于调试。
        """
        return f'{self.name}_{self.confidence:.2f}'

    def __str__(self):
        """
        Returns a detailed string representation of the Box.

        返回 Box 的详细字符串表示。
        """
        if self.name is not None:
            return f"Box(name='{self.name}', x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"
        return f"Box(x={self.x}, y={self.y}, width={self.width}, height={self.height}, confidence={round(self.confidence * 100)})"

    def scale(self, width_ratio: float, height_ratio: float = None):
        """
        Scales the box by given ratios, keeping the center the same.

        通过给定比率缩放框，保持中心不变。

        :param width_ratio: Ratio to scale the width. 宽度缩放比率。
        :param height_ratio: Ratio to scale the height (defaults to width_ratio). 高度缩放比率（默认为宽度比率）。
        :return: New scaled Box. 新的缩放框。
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

    def closest_distance(self, other):
        """
        Calculates the closest distance between two boxes.

        计算两个框之间的最近距离。

        :param other: The other Box. 另一个框。
        :return: The distance. 距离。
        """
        right1 = self.x + self.width
        bottom1 = self.y + self.height
        right2 = other.x + other.width
        bottom2 = other.y + other.height

        horizontal_distance = max(0, max(self.x, other.x) - min(right1, right2))
        vertical_distance = max(0, max(self.y, other.y) - min(bottom1, bottom2))
        return 0.0 if horizontal_distance == 0 and vertical_distance == 0 else math.sqrt(
            horizontal_distance ** 2 + vertical_distance ** 2)

    def center_distance(self, other):
        """
        Calculates the Euclidean distance between centers of two boxes.

        计算两个框中心之间的欧几里得距离。

        :param other: The other Box. 另一个框。
        :return: The distance. 距离。
        """
        x1, y1 = self.center()
        x2, y2 = other.center()
        dx = x2 - x1
        dy = y2 - y1
        return math.sqrt(float(dx ** 2 + dy ** 2))

    def relative_with_variance(self, relative_x=0.5, relative_y=0.5):
        """
        Gets a point relative to the box with random variance.

        获取相对于框的点，带有随机方差。

        :param relative_x: Relative x position (0-1). 相对 x 位置（0-1）。
        :param relative_y: Relative y position (0-1). 相对 y 位置（0-1）。
        :return: (x, y) coordinates. (x, y) 坐标。
        """
        center_x = self.x + self.width * relative_x
        center_y = self.y + self.height * relative_y
        variance = random.uniform(0, 0.1)
        return int(round(center_x + variance)), int(round(center_y + variance))

    def copy(self, x_offset=0, y_offset=0, width_offset=0, height_offset=0, name=None):
        """
        Creates a copy of the box with offsets.

        创建框的副本，带有偏移。

        :param x_offset: Offset for x. x 偏移。
        :param y_offset: Offset for y. y 偏移。
        :param width_offset: Offset for width. 宽度偏移。
        :param height_offset: Offset for height. 高度偏移。
        :param name: New name (defaults to original). 新名称（默认为原名称）。
        :return: New Box. 新框。
        """
        return Box(self.x + x_offset, self.y + y_offset, self.width + width_offset, self.height + height_offset,
                   self.confidence, name or self.name)

    def crop_frame(self, frame):
        """
        Crops the frame to this box's area.

        将帧裁剪到此框的区域。

        :param frame: The image frame. 图像帧。
        :return: Cropped frame. 裁剪后的帧。
        """
        return frame[self.y:self.y + self.height, self.x:self.x + self.width]

    def center(self):
        """
        Gets the center coordinates of the box.

        获取框的中心坐标。

        :return: (x, y) center. (x, y) 中心。
        """
        return round(self.x + self.width / 2.0), round(self.y + self.height / 2.0)

    def _distance_criteria(self, box, direction, orig_x, orig_y, orig_w, orig_h, condition=None):
        box_x = box.x
        box_y = box.y
        box_w = box.width
        box_h = box.height
        dx = max(orig_x - (box_x + box_w), box_x - (orig_x + orig_w), 0)
        dy = max(orig_y - (box_y + box_h), box_y - (orig_y + orig_h), 0)
        distance = math.sqrt(dx ** 2 + dy ** 2)
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

    def find_closest_box(self, direction, boxes, condition=None):
        """
        Finds the closest box in a given direction.

        在给定方向查找最近的框。

        :param direction: Direction ('up', 'down', 'left', 'right', 'all'). 方向。
        :param boxes: List of boxes to search. 要搜索的框列表。
        :param condition: Optional condition function. 可选条件函数。
        :return: Closest Box or None. 最近的框或 None。
        """
        orig_x = self.x
        orig_y = self.y
        orig_w = self.width
        orig_h = self.height

        boxes.sort(key=lambda box: self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition))
        for box in boxes:
            if self._distance_criteria(box, direction, orig_x, orig_y, orig_w, orig_h, condition) != float('inf'):
                return box
        return None


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
            cmp = box1.x - box2.x
    if cmp == 0:
        cmp = int(box1.confidence * 1000 - box2.confidence * 1000)
    if cmp == 0 and box1.name is not None and box2.name is not None:
        cmp = (box1.name > box2.name) - (box1.name < box2.name)
    return cmp


def find_highest_confidence_box(boxes):
    """
    Finds the box with the highest confidence.

    查找置信度最高的框。
    """
    if not boxes:
        return None
    return max(boxes, key=lambda box: box.confidence)


def sort_boxes(boxes):
    """
    Sorts boxes from top to bottom, left to right.

    从上到下、从左到右对框进行排序。
    """
    boxes.sort(key=cmp_to_key(compare_boxes))
    return boxes


def find_box_by_name(boxes, names):
    """
    Finds the first box matching any of the names.

    查找匹配任一名称的第一个框。
    """
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


def get_bounding_box(boxes):
    """
    Calculates the bounding box for a list of boxes.

    计算框列表的边界框。
    """
    if not boxes:
        raise ValueError("The list of boxes is empty")

    min_x = min(box.x for box in boxes)
    min_y = min(box.y for box in boxes)
    max_x = max(box.x + box.width for box in boxes)
    max_y = max(box.y + box.height for box in boxes)

    return Box(min_x, min_y, max_x - min_x, max_y - min_y)


def find_boxes_within_boundary(boxes, boundary_box, sort=True):
    """
    Finds boxes within a boundary box.

    查找边界框内的框。
    """
    within_boundary = []

    for box in boxes:
        if (box.x >= boundary_box.x and
                box.y >= boundary_box.y and
                box.x + box.width <= boundary_box.x + boundary_box.width and
                box.y + box.height <= boundary_box.y + boundary_box.height):
            within_boundary.append(box)
    if sort:
        within_boundary = sort_boxes(within_boundary)
    return within_boundary


def average_width(boxes):
    """
    Calculates the average width of a list of boxes.

    计算框列表的平均宽度。
    """
    total_width = sum(box.width for box in boxes)
    return int(total_width / len(boxes)) if boxes else 0


def crop_image(image, box=None):
    """
    Crops the image based on the box.

    根据框裁剪图像。
    """
    if box is not None:
        if (0 <= box.x <= image.shape[1] - box.width and
                0 <= box.y <= image.shape[0] - box.height and
                box.width > 0 and box.height > 0):
            return image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            return image
    return image


def relative_box(frame_width, frame_height, x, y, to_x=1, to_y=1, width=0, height=0, name=None, confidence=1.0):
    """
    Calculate a box coordinates relative to the frame size.

    根据帧大小计算相对框坐标。
    """
    if width == 0:
        width = to_x - x
    if height == 0:
        height = to_y - y
    return Box(round(x * frame_width), round(y * frame_height),
               round(width * frame_width), round(height * frame_height),
               name=name, confidence=confidence)


def find_boxes_by_name(boxes, names):
    """
    Finds boxes that match the given names or patterns.

    通过名称或模式查找匹配的框。

    :param boxes: List of boxes to search. 要搜索的框列表。
    :param names: Name or list of names/patterns to match. 要匹配的名称或名称/模式列表。
    :return: List of matching boxes. 匹配的框列表。
    """
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = []

    for box in boxes:
        matched = False
        for name in names:
            if matched:
                break
            if (isinstance(name, str) and name == box.name) or (isinstance(box.name, str) and
                                                                isinstance(name, re.Pattern) and re.search(name,
                                                                                                           box.name)):
                matched = True
        if matched:
            result.append(box)

    return result
