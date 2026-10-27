import importlib
import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from ok import OK, og
from ok.util.config import Config, ConfigOption
from ok.util.GlobalConfig import ENABLE_MCP_SERVER, GlobalConfig, register_basic_options
from ok.ui.qt.settings.GlobalConfigCard import GlobalConfigCard


@pytest.fixture
def setting(tmp_path, monkeypatch):
    qt_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(Config, 'config_folder', str(tmp_path))
    monkeypatch.setattr(og, 'app', SimpleNamespace(tr=lambda text: text))
    runtime = object.__new__(OK)
    runtime.config = {'mcp': {'port': 0}}
    runtime._mcp_server = None
    runtime.global_config = GlobalConfig(None)
    config = register_basic_options(runtime.global_config)
    monkeypatch.setattr(og, 'ok', runtime)
    server_class = Mock()
    server_class.return_value._thread = None
    monkeypatch.setattr('ok.core.mcp_server.LocalMcpServer', server_class)
    dialog = Mock()
    dialog.return_value.exec.return_value = True
    module = importlib.import_module('ok.ui.qt.tasks.LabelAndMcpServer')
    monkeypatch.setattr(module, 'MessageBox', dialog)
    card = GlobalConfigCard(config, runtime.global_config.config_options['Basic Options'])
    widget = card.config_widget_by_key[ENABLE_MCP_SERVER]
    yield SimpleNamespace(runtime=runtime, config=config, server=server_class,
                          dialog=dialog, widget=widget, card=card, qt_app=qt_app)
    card.deleteLater()


def test_enable_requires_confirmation_before_starting_or_persisting(setting):
    s = setting
    assert not s.config[ENABLE_MCP_SERVER]
    assert not s.widget.switch_button.isChecked()
    s.runtime.start_mcp_server()
    s.server.assert_not_called()

    def confirm():
        s.server.assert_not_called()
        assert not s.config[ENABLE_MCP_SERVER]
        return True
    s.dialog.return_value.exec.side_effect = confirm
    s.widget.switch_button.setChecked(True)

    s.server.return_value.start.assert_called_once_with()
    assert s.runtime._mcp_server is s.server.return_value
    assert s.config[ENABLE_MCP_SERVER]
    assert s.runtime.config['mcp'] == {'port': 0, 'enabled': True}


def test_cancel_leaves_server_disabled(setting):
    s = setting
    s.dialog.return_value.exec.return_value = False
    s.widget.switch_button.setChecked(True)
    s.server.assert_not_called()
    assert not s.config[ENABLE_MCP_SERVER]
    assert not s.widget.switch_button.isChecked()
    assert s.runtime.config['mcp'] == {'port': 0}


def test_failed_start_rolls_back_setting_and_shows_error(setting):
    s = setting
    s.server.return_value.start.side_effect = RuntimeError('The required MCP dependency is missing')
    s.widget.switch_button.setChecked(True)
    assert not s.config[ENABLE_MCP_SERVER]
    assert not s.widget.switch_button.isChecked()
    assert s.runtime._mcp_server is None
    assert s.runtime.config['mcp'] == {'port': 0}
    assert s.dialog.call_count == 2
    assert s.dialog.call_args.args[1] == 'The required MCP dependency is missing'


@pytest.mark.parametrize('reset', [False, True])
def test_disable_and_reset_stop_server_immediately(setting, reset):
    s = setting
    s.widget.switch_button.setChecked(True)
    s.dialog.reset_mock()
    if reset:
        s.card.reset_clicked()
    else:
        s.widget.switch_button.setChecked(False)
    s.server.return_value.stop.assert_called_once_with()
    s.server.return_value.join.assert_called_once_with()
    s.dialog.assert_not_called()
    assert s.runtime._mcp_server is None
    assert not s.config[ENABLE_MCP_SERVER]
    assert not s.widget.switch_button.isChecked()


def test_saved_opt_in_starts_on_next_launch(setting):
    s = setting
    s.widget.switch_button.setChecked(True)
    s.runtime.stop_mcp_server()
    s.runtime.config = {}  # The next launch has no CLI/config opt-in.
    s.runtime.global_config = GlobalConfig(None)
    register_basic_options(s.runtime.global_config)
    s.server.reset_mock()
    s.runtime.start_mcp_server()
    s.server.return_value.start.assert_called_once_with()
    assert s.runtime._mcp_server is s.server.return_value


def test_mcp_option_is_added_to_application_defined_basic_options(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'config_folder', str(tmp_path))
    custom = ConfigOption('Basic Options', {'Custom Setting': True})
    global_config = GlobalConfig([custom])
    config = register_basic_options(global_config)
    assert config['Custom Setting']
    assert config.get_default(ENABLE_MCP_SERVER) is False
    assert config[ENABLE_MCP_SERVER] is False
    assert custom.config_type[ENABLE_MCP_SERVER]['type'] == 'mcp_server'
