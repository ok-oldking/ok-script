"""Discover consumer-application skills from source or an installed distribution."""

from pathlib import Path


def skill_root():
    checkout = Path(__file__).resolve().parents[2]
    if (checkout / 'pyproject.toml').is_file() and (checkout / '.agents/skills').is_dir():
        return checkout / '.agents/skills'
    return Path(__file__).resolve().parents[1] / 'agent_resources/.agents/skills'


def list_skills():
    """Return lightweight metadata and local paths without loading skill bodies."""
    skills = []
    for path in sorted(skill_root().glob('*/SKILL.md')):
        content = path.read_text(encoding='utf-8')
        metadata = {}
        lines = content.splitlines()
        if lines and lines[0] == '---':
            for line in lines[1:]:
                if line == '---':
                    break
                key, separator, value = line.partition(':')
                if separator:
                    metadata[key] = value.strip()
        skills.append({
            'id': path.parent.name,
            'name': metadata.get('name', path.parent.name),
            'description': metadata.get('description', ''),
            'uri': f'ok-script://skills/{path.parent.name}',
            'path': str(path),
        })
    return skills


def get_skill(skill_id):
    """Read only a discovered skill; never interpret an ID as an arbitrary path."""
    for skill in list_skills():
        if skill['id'] == skill_id:
            return {**skill, 'content': Path(skill['path']).read_text(encoding='utf-8')}
    raise ValueError(f'Unknown skill: {skill_id}')
