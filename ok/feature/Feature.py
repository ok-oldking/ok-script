import numpy as np


class Feature:
    def __init__(self, mat: np.ndarray, x: int, y: int, width: int, height: int) -> None:
        """
        Initialize a Feature with an image (Mat) and its bounding box coordinates.

        Args:
            mat (np.ndarray): The OpenCV Mat object representing the image.
            x (int): The x-coordinate of the top-left corner of the bounding box.
            y (int): The y-coordinate of the top-left corner of the bounding box.
            width (int): The width of the bounding box.
            height (int): The height of the bounding box.
        """
        self.mat = mat
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __str__(self) -> str:
        return f'self.x: {self.x}, self.y: {self.y}, width: {self.width}, height: {self.height}'
