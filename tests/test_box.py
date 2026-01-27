import unittest

from ok import Logger
from ok.feature.Box import Box, sort_boxes

logger = Logger.get_logger(__name__)


class TestBox(unittest.TestCase):

    def test_sort_box(self):
        logger.debug("start test_check_for_updates")
        # Create an Updater instance with a mocked config
        box1 = Box(0, 10, 10, 10)
        box2 = Box(10, 10, 10, 10)
        box_list = [box2, box1]
        box_list_sorted = sort_boxes(box_list)

        # Assert the function returned the expected result
        self.assertEqual([box1, box2], box_list_sorted)

        box1 = Box(120, 740, 147, 38, name='41乐进', confidence=0.9998183)
        box2 = Box(461, 736, 149, 41, name='41左慈', confidence=0.99900174)
        box_list = [box2, box1]
        box_list_sorted = sort_boxes(box_list)
        self.assertEqual([box1, box2], box_list_sorted)


if __name__ == '__main__':
    unittest.main()
