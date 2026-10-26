from pathlib import Path

import pytest

from ok.core import skills


def test_checkout_skills_are_discovered_independently_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    catalog = {skill['id']: skill for skill in skills.list_skills()}
    assert {'develop', 'setup-env', 'setup-project', 'use_venv'} <= catalog.keys()
    assert catalog['use_venv']['name'] == 'use-venv'
    for skill in catalog.values():
        assert skill['description']
        assert Path(skill['path']).is_absolute()
        assert skills.get_skill(skill['id'])['content'] == Path(skill['path']).read_text(encoding='utf-8')


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


@pytest.mark.parametrize('skill_id', ['missing', '../setup.py', '../../AGENTS.md', '/etc/passwd'])
def test_unknown_skill_cannot_read_arbitrary_files(skill_id):
    with pytest.raises(ValueError, match='Unknown skill'):
        skills.get_skill(skill_id)
