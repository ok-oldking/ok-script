import os
from pathlib import Path
import shutil
import setuptools
from setuptools.command.build_py import build_py


class BuildPyWithSkills(build_py):
    """Bundle the canonical repository skills without maintaining a second copy."""

    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        destination = Path(self.build_lib) / 'ok' / 'agent_resources'
        # Retain the repository layout so relative skill links still resolve.
        shutil.copytree(root / '.agents/skills', destination / '.agents/skills',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for relative in ('pyproject.toml', 'docs/mcp.md', 'examples/mcp_observe.py'):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, target)

os.environ["PYTHONIOENCODING"] = "utf-8"

VERSION_NUM = os.environ.get('OK_SCRIPT_BUILD_VERSION')
if VERSION_NUM:
    print(f'building explicit version {VERSION_NUM}')
else:
    from get_pypi_latest_version import GetPyPiLatestVersion

    obtainer = GetPyPiLatestVersion()
    latest_version = obtainer("ok-script")
    VERSION_NUM = obtainer.version_add_one(latest_version, add_patch=True)
    print(f'latest_version is {latest_version} new version is {VERSION_NUM}')

setuptools.setup(version=VERSION_NUM, cmdclass={'build_py': BuildPyWithSkills})
