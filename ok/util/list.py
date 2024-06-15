def get_first_item(lst, default=None):
    return next(iter(lst), default) if lst is not None else default


def safe_get(lst, idx, default=None):
    try:
        return lst[idx]
    except IndexError:
        return default
