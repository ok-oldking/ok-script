import importlib


def init_class_by_name(module_name, class_name, *args, **kwargs):
    module = importlib.import_module(module_name)
    class_ = getattr(module, class_name)
    return class_(*args, **kwargs)
