from ok.util.logger import config_logger


def test_config_logger_does_not_create_file_log_during_pytest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_logger({"debug": False})

    assert not (tmp_path / "logs").exists()
