from pathlib import Path
import re
import runpy
from unittest.mock import Mock

import pytest

from ok.core import skills

CONSUMER_SKILLS = {'develop', 'reload-tasks', 'generate-templates', 'setup-env',
                   'setup-project', 'use_venv', 'write-test'}


def assert_skill_links_resolve(catalog):
    for skill in catalog:
        source = Path(skill['path'])
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', source.read_text(encoding='utf-8')):
            if '://' not in target and not target.startswith('#'):
                assert (source.parent / target.split('#')[0]).resolve().is_file(), target


def test_checkout_skills_are_discovered_independently_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    catalog = {skill['id']: skill for skill in skills.list_skills()}
    assert catalog.keys() == CONSUMER_SKILLS
    assert catalog['use_venv']['name'] == 'use-venv'
    for skill in catalog.values():
        assert skill['description']
        assert Path(skill['path']).is_absolute()
        assert skills.get_skill(skill['id'])['content'] == Path(skill['path']).read_text(encoding='utf-8')
    assert_skill_links_resolve(catalog.values())


def test_installed_skills_use_bundled_files(tmp_path, monkeypatch):
    package = tmp_path / 'ok'
    monkeypatch.setattr(skills, '__file__', str(package / 'core/skills.py'))
    skill = package / 'agent_resources/.agents/skills/example/SKILL.md'
    skill.parent.mkdir(parents=True)
    content = '---\nname: example\ndescription: Bundled example.\n---\nInstructions.\n'
    skill.write_text(content, encoding='utf-8')
    assert skills.list_skills() == [{
        'id': 'example', 'name': 'example', 'description': 'Bundled example.',
        'uri': 'ok-script://skills/example', 'path': str(skill),
    }]
    assert skills.get_skill('example')['content'] == content


def test_incremental_build_bundles_only_current_consumer_skills(tmp_path, monkeypatch):
    import setuptools
    from setuptools.command.build_py import build_py

    monkeypatch.setenv('OK_SCRIPT_BUILD_VERSION', '0.0.0+test')
    monkeypatch.setattr(setuptools, 'setup', Mock())
    monkeypatch.setattr(build_py, 'run', lambda self: None)
    root = Path(__file__).resolve().parents[1]
    command_class = runpy.run_path(str(root / 'setup.py'))['BuildPyWithSkills']
    command = command_class(setuptools.Distribution())
    command.build_lib = str(tmp_path / 'build')
    destination = Path(command.build_lib) / 'ok/agent_resources'
    stale = destination / '.agents/skills/deploy_pip/SKILL.md'
    stale.parent.mkdir(parents=True)
    stale.write_text('old maintainer skill', encoding='utf-8')

    command.run()

    assert not stale.exists()
    assert not (destination / 'pyproject.toml').exists()
    assert (destination / 'docs/agent-setup.md').read_bytes() == (root / 'docs/agent-setup.md').read_bytes()
    template = Path('.agents/skills/setup-env/assets/ok-script-develop/SKILL.md')
    assert (destination / template).read_bytes() == (root / template).read_bytes()
    monkeypatch.setattr(skills, '__file__', str(Path(command.build_lib) / 'ok/core/skills.py'))
    catalog = skills.list_skills()
    assert {skill['id'] for skill in catalog} == CONSUMER_SKILLS
    assert_skill_links_resolve(catalog)
    for skill in catalog:
        assert skills.get_skill(skill['id'])['content'] == (
            root / '.agents/skills' / skill['id'] / 'SKILL.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('skill_id', ['missing', '../setup.py', '../../AGENTS.md', '/etc/passwd',
                                     'commit_changes', 'deploy_pip', 'compile_i18n'])
def test_unknown_skill_cannot_read_arbitrary_files(skill_id):
    with pytest.raises(ValueError, match='Unknown skill'):
        skills.get_skill(skill_id)
