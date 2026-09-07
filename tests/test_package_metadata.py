import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _metadata():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_profiles_are_consistent_and_headless_by_default():
    metadata = _metadata()
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
    assert any(requirement.startswith("pynput>=1.8.1;") for requirement in project["dependencies"])

    managed_requirements = [
        *project["dependencies"],
        *(requirement for profile in extras.values() for requirement in profile),
    ]
    assert not any("opencv" in requirement.lower() for requirement in managed_requirements)


def test_windows_only_dependencies_have_platform_markers():
    dependencies = _metadata()["project"]["dependencies"]
    for package_name in ("pywin32", "pydirectinput", "pycaw", "mouse", "pynput"):
        requirement = next(
            item for item in dependencies
            if item.lower().startswith(package_name.lower())
        )
        assert "sys_platform == 'win32'" in requirement


def test_macos_framework_dependencies_have_platform_markers():
    dependencies = _metadata()["project"]["dependencies"]
    for package_name in (
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-Quartz",
        "pyobjc-framework-ScreenCaptureKit",
        "pyobjc-framework-ApplicationServices",
    ):
        requirement = next(
            item for item in dependencies
            if item.lower().startswith(package_name.lower())
        )
        assert "sys_platform == 'darwin'" in requirement


def test_d3dshot_default_extra_is_windows_only():
    metadata = _metadata()
    project_default = metadata["project"]["optional-dependencies"]["default"]
    dependency_default = metadata["dependency-groups"]["default"]
    for requirements in (project_default, dependency_default):
        d3dshot = next(item for item in requirements if item.startswith("ok-d3dshot"))
        assert "sys_platform == 'win32'" in d3dshot


def test_setup_metadata_is_deterministic_and_offline_safe():
    setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert "get_pypi_latest_version" not in setup_source
    assert "OK_SCRIPT_BUILD_VERSION" in setup_source
    assert "2.0.7.dev0" in setup_source


def test_legacy_requirements_files_are_replaced_by_pyproject_groups():
    assert not (ROOT / "requirements.txt").exists()
    assert not (ROOT / "requirements-docs.txt").exists()
