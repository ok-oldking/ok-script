import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_pyproject_keeps_runtime_and_development_dependencies_separate():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    extras = project["optional-dependencies"]
    groups = metadata["dependency-groups"]

    assert set(extras) == {"web", "qt"}
    assert {item["include-group"] for item in groups["default"] if isinstance(item, dict)} == {
        "web", "qt",
    }
    assert any(
        isinstance(requirement, str) and requirement.startswith("pytest")
        for requirement in groups["default"]
    )
    assert not any(requirement.startswith("pytest") for requirement in project["dependencies"])


def test_legacy_requirements_files_are_replaced_by_pyproject_groups():
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-docs.txt").exists()
