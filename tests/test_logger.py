import logging
from unittest.mock import Mock

import pytest

import ok.util.logger as logger_module
from ok.util.logger import SafeFileHandler, config_logger


@pytest.mark.parametrize("use_exception_message", [False, True])
def test_logger_exception_preserves_original_traceback(caplog, use_exception_message):
    logger = logger_module.Logger.get_logger("ok.ui.qt.MainWindow")
    logger.logger = logging.getLogger("test.logger_exception")

    try:
        raise RuntimeError("schedule resolution failed")
    except RuntimeError as error:
        logger.exception(error if use_exception_message else "schedule task index sync failed in __init__")

    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith("MainWindow:")
    assert record.exc_info[0] is RuntimeError
    assert str(record.exc_info[1]) == "schedule resolution failed"
    assert "Traceback (most recent call last)" in caplog.text
    assert "RuntimeError: schedule resolution failed" in caplog.text


def test_config_logger_does_not_create_file_log_during_pytest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_logger({"debug": False})

    assert not (tmp_path / "logs").exists()


def test_safe_file_handler_ignores_records_after_close(tmp_path, capsys):
    handler = SafeFileHandler(tmp_path / "test.log", when="midnight")
    handler.close()

    handler.emit(logging.makeLogRecord({"msg": "late shutdown message"}))

    assert capsys.readouterr().err == ""


def test_config_logger_detaches_queue_handler_before_stopping_listener(monkeypatch):
    queue_handler = Mock(spec=logging.Handler)
    listener = Mock()
    file_handler = Mock(spec=logging.Handler)
    logger_module._ok_logger.addHandler(queue_handler)
    logger_module._queue_handler = queue_handler
    logger_module._file_listener = listener
    logger_module._file_handler = file_handler

    monkeypatch.setattr(logger_module, "_should_skip_file_logging", lambda config: True)
    monkeypatch.setattr(logger_module, "CommunicateHandler", logging.NullHandler)

    def assert_queue_handler_was_detached():
        assert queue_handler not in logger_module._ok_logger.handlers

    listener.stop.side_effect = assert_queue_handler_was_detached

    config_logger({"debug": False})

    listener.stop.assert_called_once_with()
    queue_handler.close.assert_called_once_with()
    file_handler.close.assert_called_once_with()
