import pytest

from ok.util.version import compare_versions


@pytest.mark.parametrize('left,right', [
    ('1.10', '1.9'), ('v2.0.15b1', '2.0.14'), ('1.0a2', '1.0a1'),
    ('1.0b1', '1.0a99'), ('1.0rc1', '1.0b99'), ('1.0', '1.0rc99'),
    ('1.0a1', '1.0a1.dev2'), ('1.0a0', '1.0.dev99'),
    ('1.0.post1', '1.0'), ('1.0.post1', '1.0.post1.dev1'),
    ('1.0.post1.dev1', '1.0'), ('1!0.1', '999.0'),
    ('1.0+build.10', '1.0+build.9'), ('1.0+1', '1.0+abc'),
    ('1.0+build', '1.0'), ('1.0.0.1', '1.0'), ('0.0.1', '0'),
])
def test_version_order(left, right):
    assert compare_versions(left, right) == 1
    assert compare_versions(right, left) == -1


@pytest.mark.parametrize('left,right', [
    ('1.2', '1.2.0'), ('0', '0.0.0'), (' V1.2.3 ', '1.2.3'),
    ('1.0-beta.1', '1.0b1'), ('1.0-preview.2', '1.0rc2'),
    ('1.0alpha', '1.0a0'), ('1.0-1', '1.0.post1'),
    ('1.0rev2', '1.0.post2'), ('1.0dev', '1.0.dev0'),
    ('1.0+BUILD-1', '1.0+build.1'), ('0!1.0', '1'),
])
def test_equivalent_versions(left, right):
    assert compare_versions(left, right) == 0


@pytest.mark.parametrize('version', ['', 'dev', 'release-1.0', '1..2', '1.2garbage',
                                    'v', '1.*', '>=1.0', '1.0+', '1.0+abc..1', None, 1.2])
def test_invalid_versions_raise(version):
    with pytest.raises(ValueError, match='Invalid version'):
        compare_versions(version, '1.0')


def test_qt_plugin_startup_import_does_not_need_packaging():
    import os
    import subprocess
    import sys
    from pathlib import Path

    source = '''
import sys
sys.modules['packaging'] = None
from ok.ui.qt.plugins.imported_tabs import ImportedTabs
from ok.core.plugins import newer_plugin_version
assert newer_plugin_version('v2.0.15b1', '2.0.14')
assert newer_plugin_version('2.0.15', '2.0.15b1')
assert not newer_plugin_version('1.2', '1.2.0')
'''
    result = subprocess.run(
        [sys.executable, '-c', source], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
