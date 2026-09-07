from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ok.ui.qt.tasks import TaskCard as module


@pytest.mark.parametrize('status,allowed', [
    ('experimental', True), ('validated', True),
    ('unsupported', False), ('missing-capabilities', False),
])
@pytest.mark.parametrize('platform,visible', [('darwin', False), ('win32', True)])
def test_compact_labels_do_not_change_capability_gate(monkeypatch, status, allowed, platform, visible):
    monkeypatch.setattr(module, 'sys', SimpleNamespace(platform=platform))
    state = dict(status=status, level='MAC_BASIC', missing=('scroll',), reason='details')
    card = SimpleNamespace(
        task=SimpleNamespace(get_device_compatibility_state=lambda: state),
        compatibility_label=Mock(), card=SimpleNamespace(titleLabel=Mock()))
    assert module.TaskCard.update_compatibility(card) is allowed
    card.compatibility_label.setVisible.assert_called_once_with(visible)
    if platform == 'darwin':
        card.card.titleLabel.setToolTip.assert_called_once_with('details')


@pytest.mark.parametrize('status,allowed', [('missing-capabilities', True), ('unsupported', False)])
def test_onetime_start_can_request_macos_connection(monkeypatch, status, allowed):
    monkeypatch.setattr(module, 'macos_device_selected', lambda: True)
    card = SimpleNamespace(onetime=True,
        task=SimpleNamespace(get_device_compatibility_state=lambda: dict(status=status)),
        compatibility_label=Mock(), card=SimpleNamespace(titleLabel=Mock()))
    assert module.TaskCard.update_compatibility(card) is allowed
