from qfluentwidgets.components.widgets.spin_box import CompactSpinBox, SpinBoxBase


class OkCompactSpinBox(CompactSpinBox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def focusInEvent(self, e):
        super(SpinBoxBase, self).focusInEvent(e)
