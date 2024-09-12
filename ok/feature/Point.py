import re


class Point:
    def __init__(self, x: int | float, y: int | float, name=None) -> None:
        self.name = name
        self.x = round(x)
        self.y = round(y)

def find_point_by_name(points, names) -> Point:
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = None
    priority = len(names)

    for point in points:
        for i, name in enumerate(names):
            if (isinstance(name, str) and name == point.name) or (
                    isinstance(name, re.Pattern) and re.search(name, point.name)):
                if i < priority:
                    priority = i
                    result = point
                    if i == 0:
                        break

    return result

def find_points_by_name(points, names) -> list[Point]:
    # Ensure names is always a list
    if isinstance(names, (str, re.Pattern)):
        names = [names]

    result = []

    for point in points:
        # Flag to track if the box has been matched and should be added
        matched = False
        for name in names:
            if matched:
                break  # Stop checking names if we've already matched this box
            if (isinstance(name, str) and name == point.name) or (isinstance(point.name, str) and
                                                                isinstance(name, re.Pattern) and re.search(name,
                                                                                                           point.name)):
                matched = True
        if matched:
            result.append(point)

    return result