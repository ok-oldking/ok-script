class UpdateConfigWidgetItem:
    def __init__(self, config, key, value):
        self.key = key
        self.config = config
        self.value = value

    def set_value(self, value):
        self.config[self.key] = value
        self.value = value


def value_to_string(obj):
    if isinstance(obj, list):
        return ', '.join(map(str, obj))
    else:
        return str(obj)
