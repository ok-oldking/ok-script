from ok.update import inline_ok_requirements


def _write_repo_files(repo_dir, deploy_text=None):
    (repo_dir / "config.py").write_text('version = "v0.0.0"\n', encoding="utf-8")
    (repo_dir / "requirements.txt").write_text(
        "ok-script==1.0.147\npyappify==1.0.3\nrequests==2.32.3\n",
        encoding="utf-8",
    )
    if deploy_text is not None:
        (repo_dir / "deploy.txt").write_text(deploy_text, encoding="utf-8")


def test_remove_ok_requirements_always_includes_defaults_without_deploy_txt(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path)
    (tmp_path / "requirements-web.txt").write_text(
        "ok-script==1.0.147\npyappify==1.0.3\nhttpx==0.28.1\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements-dev.txt").write_text(
        "PYAPPIFY==1.0.3\npytest==8.4.1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(str(tmp_path), "v1.2.3")

    assert copied_folders == ["ok", "pyappify"]
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "requests==2.32.3\n"
    )
    assert (tmp_path / "requirements-web.txt").read_text(encoding="utf-8") == (
        "httpx==0.28.1\n"
    )
    assert (tmp_path / "requirements-dev.txt").read_text(encoding="utf-8") == (
        "pytest==8.4.1\n"
    )
    assert (tmp_path / "deploy.txt").read_text(encoding="utf-8") == "ok\npyappify\n"
    assert (tmp_path / "config.py").read_text(encoding="utf-8") == 'version = "v1.2.3"\n'


def test_remove_ok_requirements_adds_missing_defaults_to_deploy_txt(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path, "src\nok\nrequirements.txt\n")
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(str(tmp_path), "v1.2.3")

    assert copied_folders == ["ok", "pyappify"]
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "requests==2.32.3\n"
    )
    assert (tmp_path / "deploy.txt").read_text(encoding="utf-8") == (
        "src\nok\nrequirements.txt\npyappify\n"
    )


def test_remove_ok_requirements_matches_deploy_subpaths(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path, "pyappify/main.py\n")
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(str(tmp_path), "v1.2.3")

    assert copied_folders == ["ok", "pyappify"]
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "requests==2.32.3\n"
    )
    assert (tmp_path / "deploy.txt").read_text(encoding="utf-8") == "pyappify/main.py\nok\n"


def test_additional_inlined_requirement_is_added_to_deploy_and_removed(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path, "src")
    with (tmp_path / "requirements.txt").open("a", encoding="utf-8") as requirements:
        requirements.write("custom-package==2.0.0\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.main([
        "--tag",
        "v1.2.3",
        "--add-inlined-requirement",
        "custom-package=custom_package",
    ])

    assert copied_folders == ["ok", "pyappify", "custom_package"]
    assert (tmp_path / "deploy.txt").read_text(encoding="utf-8") == (
        "src\nok\npyappify\ncustom_package\n"
    )
    assert "custom-package" not in (tmp_path / "requirements.txt").read_text(encoding="utf-8")


def test_additional_inlined_requirement_does_not_duplicate_deploy_subpath(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path, "custom_package/main.py\n")
    with (tmp_path / "requirements.txt").open("a", encoding="utf-8") as requirements:
        requirements.write("custom-package==2.0.0\n")
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(
        str(tmp_path),
        "v1.2.3",
        {"custom-package": "custom_package"},
    )

    assert copied_folders == ["ok", "pyappify", "custom_package"]
    assert (tmp_path / "deploy.txt").read_text(encoding="utf-8") == (
        "custom_package/main.py\nok\npyappify\n"
    )
