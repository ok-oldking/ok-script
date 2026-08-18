from ok.gui.tasks.LabelAndButtons import LabelAndButtons as LegacyLabelAndButtons
from ok.gui.tasks.LabelAndFileSelector import LabelAndFileSelector as LegacyLabelAndFileSelector
from ok.gui.tasks.ModifyListItem import ModifyListItem as LegacyModifyListItem
from ok.ui.qt.tasks.LabelAndButtons import LabelAndButtons
from ok.ui.qt.tasks.LabelAndFileSelector import LabelAndFileSelector
from ok.ui.qt.tasks.ModifyListItem import ModifyListItem


def test_legacy_qt_imports_reuse_current_module_classes():
    assert LegacyLabelAndButtons is LabelAndButtons
    assert LegacyLabelAndFileSelector is LabelAndFileSelector
    assert LegacyModifyListItem is ModifyListItem
