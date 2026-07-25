from types import SimpleNamespace
from unittest.mock import Mock

from ok.feature.FeatureSet import FeatureSet
from ok.task.task import FindFeature, OCR


def test_find_feature_returns_empty_when_frame_is_none():
    feature_set = Mock()
    operation = FindFeature.__new__(FindFeature)
    operation._executor = SimpleNamespace(frame=None, feature_set=feature_set)

    assert operation.find_feature("loading") == []
    feature_set.find_feature.assert_not_called()


def test_ocr_returns_empty_when_frame_is_none():
    operation = OCR.__new__(OCR)
    operation._executor = SimpleNamespace(frame=None)

    assert operation.ocr() == []


def test_feature_set_searches_return_empty_when_frame_is_none():
    feature_set = FeatureSet.__new__(FeatureSet)

    assert feature_set.find_feature(None, "loading") == []
    assert feature_set.find_one_feature(None, "loading") == []
    assert feature_set.get_feature_by_name(None, "loading") is None
    assert feature_set.get_box_by_name(None, "loading") is None
