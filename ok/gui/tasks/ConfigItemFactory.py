from ok.gui.tasks.LabelAndDoubleSpinBox import LabelAndDoubleSpinBox
from ok.gui.tasks.LabelAndDropDown import LabelAndDropDown
from ok.gui.tasks.LabelAndLineEdit import LabelAndLineEdit
from ok.gui.tasks.LabelAndSpinBox import LabelAndSpinBox
from ok.gui.tasks.LabelAndSwitchButton import LabelAndSwitchButton
from ok.gui.tasks.ModifyListItem import ModifyListItem


def config_widget(task, key, value):
    the_type = task.config_type.get(key)
    if the_type:
        if the_type['type'] == 'drop_down':
            return LabelAndDropDown(task, the_type['options'], key)
    if isinstance(value, bool):
        return LabelAndSwitchButton(task, key)
    elif isinstance(value, list):
        return ModifyListItem(task, key)
    elif isinstance(value, int):
        return LabelAndSpinBox(task, key)
    elif isinstance(value, float):
        return LabelAndDoubleSpinBox(task, key)
    elif isinstance(value, str):
        return LabelAndLineEdit(task, key)
    else:
        raise ValueError(f"invalid type {type(value)}, value {value}")
