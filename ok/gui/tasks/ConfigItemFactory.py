from ok.gui.tasks.LabelAndDoubleSpinBox import LabelAndDoubleSpinBox
from ok.gui.tasks.LabelAndLineEdit import LabelAndLineEdit
from ok.gui.tasks.LabelAndSpinBox import LabelAndSpinBox
from ok.gui.tasks.LabelAndSwitchButton import LabelAndSwitchButton
from ok.gui.tasks.ModifyListItem import ModifyListItem


def config_widget(config, config_desc, key, value):
    if isinstance(value, bool):
        return LabelAndSwitchButton(config, config_desc, key)
    elif isinstance(value, list):
        return ModifyListItem(config, config_desc, key)
    elif isinstance(value, int):
        return LabelAndSpinBox(config, config_desc, key)
    elif isinstance(value, float):
        return LabelAndDoubleSpinBox(config, config_desc, key)
    elif isinstance(value, str):
        return LabelAndLineEdit(config, config_desc, key)
    else:
        raise ValueError(f"invalid type {type(value)}, value {value}")
