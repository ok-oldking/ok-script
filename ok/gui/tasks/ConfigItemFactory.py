from ok.gui.tasks.LabelAndDoubleSpinBox import LabelAndDoubleSpinBox
from ok.gui.tasks.LabelAndDropDown import LabelAndDropDown
from ok.gui.tasks.LabelAndLineEdit import LabelAndLineEdit
from ok.gui.tasks.LabelAndMultiSelection import LabelAndMultiSelection
from ok.gui.tasks.LabelAndSpinBox import LabelAndSpinBox
from ok.gui.tasks.LabelAndSwitchButton import LabelAndSwitchButton
from ok.gui.tasks.ModifyListItem import ModifyListItem


def config_widget(config_type, config_desc, config, key, value):
    the_type = config_type.get(key) if config_type is not None else None
    if the_type:
        if the_type['type'] == 'drop_down':
            return LabelAndDropDown(config_desc, the_type['options'], config, key)
        elif the_type['type'] == 'multi_selection':
            return LabelAndMultiSelection(config_desc, the_type['options'], config, key)
        else:
            raise Exception('Unknown config type')
    if isinstance(value, bool):
        return LabelAndSwitchButton(config_desc, config, key)
    elif isinstance(value, list):
        return ModifyListItem(config_desc, config, key)
    elif isinstance(value, int):
        return LabelAndSpinBox(config_desc, config, key)
    elif isinstance(value, float):
        return LabelAndDoubleSpinBox(config_desc, config, key)
    elif isinstance(value, str):
        return LabelAndLineEdit(config_desc, config, key)
    else:
        raise ValueError(f"invalid type {type(value)}, value {value}")
