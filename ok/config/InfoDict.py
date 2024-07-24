class InfoDict(dict):

    def __delitem__(self, key):
        super().__delitem__(key)

    def clear(self):
        super().clear()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
