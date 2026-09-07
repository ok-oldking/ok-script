from unittest.mock import Mock

import pytest

from ok.device.services import paths


@pytest.mark.parametrize('platform', ['darwin', 'win32'])
def test_open_local_path_dispatch_without_shell(tmp_path, monkeypatch, platform):
    item = tmp_path / 'a space;$(not-a-command)'
    item.mkdir()
    run, start = Mock(), Mock()
    monkeypatch.setattr(paths.sys, 'platform', platform)
    monkeypatch.setattr(paths.subprocess, 'run', run)
    monkeypatch.setattr(paths.os, 'startfile', start, raising=False)
    paths.open_path(item)
    if platform == 'darwin':
        run.assert_called_once_with(['/usr/bin/open', str(item)], check=True, timeout=5)
        start.assert_not_called()
    else:
        start.assert_called_once_with(str(item))
        run.assert_not_called()


def test_missing_path_is_not_opened(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.open_path(tmp_path / 'absent')
