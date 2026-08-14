from unittest.mock import patch

from ok.device.interaction_methods.base import BaseInteraction


def test_send_key_rate_limits_repeated_key_logs():
    interaction = BaseInteraction(capture=None)

    with patch("ok.device.interaction_methods.base.time.monotonic",
               side_effect=[0.0, 0.1, 0.9, 1.0]), \
            patch("ok.device.interaction_methods.base.logger.debug") as debug:
        for _ in range(4):
            interaction.send_key("f")

    assert [call.args[0] for call in debug.call_args_list] == [
        "Sending key f",
        "Sending key f",
    ]


def test_send_key_logs_different_keys_independently():
    interaction = BaseInteraction(capture=None)

    with patch("ok.device.interaction_methods.base.time.monotonic",
               side_effect=[0.0, 0.1, 0.2]), \
            patch("ok.device.interaction_methods.base.logger.debug") as debug:
        interaction.send_key("f")
        interaction.send_key("g")
        interaction.send_key("f")

    assert [call.args[0] for call in debug.call_args_list] == [
        "Sending key f",
        "Sending key g",
    ]
