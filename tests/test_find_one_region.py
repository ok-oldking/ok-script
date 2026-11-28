from types import SimpleNamespace
from unittest.mock import Mock

from ok.task.task import FindFeature


def test_find_one_passes_search_region_to_feature_set():
    feature_set = Mock()
    feature_set.find_feature.return_value = []
    operation = FindFeature.__new__(FindFeature)
    operation._executor = SimpleNamespace(frame=object(), feature_set=feature_set)

    operation.find_one("loading", x=0.1, y=0.2, to_x=0.3, to_y=0.4, width=0.5, height=0.6)

    # image, name, horizontal_variance, vertical_variance, threshold, use_gray_scale,
    # then x, y, to_x, to_y, width, height
    assert feature_set.find_feature.call_args.args[6:] == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
