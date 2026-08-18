import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_pyproject_profiles_are_consistent_and_headless_by_default():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    extras = project["optional-dependencies"]
    groups = metadata["dependency-groups"]

    assert set(extras) == {"default", "web", "qt", "adb", "ocr", "dev"}
    assert extras == groups
    assert extras["adb"] == ["adbutils>=2.2.1"]
    assert extras["ocr"] == ["onnxocr-ppocrv5"]
    assert not any(
        requirement.startswith(("fastapi", "PySide6"))
        for requirement in extras["default"]
    )
    assert any(requirement.startswith("pytest") for requirement in extras["dev"])
    assert not any(requirement.startswith("pytest") for requirement in project["dependencies"])
    assert "pynput>=1.8.1" in project["dependencies"]

    managed_requirements = [
        *project["dependencies"],
        *(requirement for profile in extras.values() for requirement in profile),
    ]
    assert not any("opencv" in requirement.lower() for requirement in managed_requirements)


def test_legacy_requirements_files_are_replaced_by_pyproject_groups():
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-docs.txt").exists()
