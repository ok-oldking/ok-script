from ok.gui.tasks.LabelAndDoubleSpinBox import LabelAndDoubleSpinBox
from ok.gui.tasks.LabelAndDropDown import LabelAndDropDown
from ok.gui.tasks.LabelAndGlobal import LabelAndGlobal
from ok.gui.tasks.LabelAndLineEdit import LabelAndLineEdit
from ok.gui.tasks.LabelAndMultiSelection import LabelAndMultiSelection
from ok.gui.tasks.LabelAndSpinBox import LabelAndSpinBox
from ok.gui.tasks.LabelAndSwitchButton import LabelAndSwitchButton
from ok.gui.tasks.LabelAndTextEdit import LabelAndTextEdit
from ok.gui.tasks.ModifyListItem import ModifyListItem


def config_widget(config_type, config_desc, config, key, value, task):
    the_type = config_type.get(key) if config_type is not None else None
    if the_type:
        if the_type['type'] == 'drop_down':
            return LabelAndDropDown(config_desc, the_type['options'], config, key)
        elif the_type['type'] == 'multi_selection':
            return LabelAndMultiSelection(config_desc, the_type['options'], config, key)
        elif the_type['type'] == 'global':
            config = task.get_global_config(key)
            desc = task.get_global_config_desc(key)
            return LabelAndGlobal(desc, config, key)
        elif the_type['type'] == 'text_edit':
            return LabelAndTextEdit(config_desc, config, key)
        else:
            raise Exception('Unknown config type')
    value = config.get_default(key)
    if isinstance(value, bool):
        return LabelAndSwitchButton(config_desc, config, key)
    elif isinstance(value, list):
        return ModifyListItem(config_desc, config, key)
    elif isinstance(value, int):
        return LabelAndSpinBox(config_desc, config, key)
    elif isinstance(value, float):
        return LabelAndDoubleSpinBox(config_desc, config, key)
    elif isinstance(value, str):
        if value and len(value) > 16 or '\n' in value:
            return LabelAndTextEdit(config_desc, config, key)
        else:
            return LabelAndLineEdit(config_desc, config, key)
    else:
        raise ValueError(f"invalid type {type(value)}, value {value}")
