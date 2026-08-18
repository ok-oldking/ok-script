from unittest.mock import Mock, call

from ok.ui.qt.start.StartTab import StartTab


def test_overlay_switch_initial_state_skips_animation():
    switch = Mock()
    switch.indicator = Mock()
    switch.indicator.slideAni = Mock()

    StartTab._set_switch_initial_state(switch, True)

    assert switch.indicator.blockSignals.call_args_list == [call(True), call(False)]
    switch.indicator.setChecked.assert_called_once_with(True)
    switch.indicator.slideAni.stop.assert_called_once_with()
    switch.indicator.setSliderX.assert_called_once_with(25)
    switch._updateText.assert_called_once_with()
