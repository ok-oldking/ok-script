import statistics


def get_first_item(lst, default=None):
    return next(iter(lst), default) if lst is not None else default


def safe_get(lst, idx, default=None):
    try:
        return lst[idx]
    except IndexError:
        return default


def find_index_in_list(my_list, target_string, default_index=-1):
    try:
        index = my_list.index(target_string)
        return index
    except ValueError:
        return default_index


def get_median(my_list):
    if not my_list:  # Check if the list is empty
        return 0
    return statistics.median(my_list)


def parse_ratio(ratio_str):
    if ratio_str:
        # Split the string into two parts: '16' and '9'
        numerator, denominator = ratio_str.split(':')
        # Convert the strings to integers and perform the division
        ratio_float = int(numerator) / int(denominator)
        return ratio_float


def deep_get(d, keys, default=None):
    """
    Get values in dictionary safely.
    https://stackoverflow.com/questions/25833613/safe-method-to-get-value-of-nested-dictionary

    Args:
        d (dict):
        keys (str, list): Such as `Scheduler.NextRun.value`
        default: Default return if key not found.

    Returns:

    """
    if isinstance(keys, str):
        keys = keys.split('.')
    assert type(keys) is list
    if d is None:
        return default
    if not keys:
        return d
    return deep_get(d.get(keys[0]), keys[1:], default)
