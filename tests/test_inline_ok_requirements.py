from ok.update import inline_ok_requirements


def _write_repo_files(repo_dir, deploy_text=None):
    (repo_dir / "config.py").write_text('version = "v0.0.0"\n', encoding="utf-8")
    (repo_dir / "requirements.txt").write_text(
        "ok-script==1.0.147\npyappify==1.0.3\nrequests==2.32.3\n",
        encoding="utf-8",
    )
    if deploy_text is not None:
        (repo_dir / "deploy.txt").write_text(deploy_text, encoding="utf-8")


def test_remove_ok_requirements_skips_inline_and_removal_without_deploy_txt(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path)
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(str(tmp_path), "v1.2.3")

    assert copied_folders == []
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "ok-script==1.0.147\npyappify==1.0.3\nrequests==2.32.3\n"
    )
    assert (tmp_path / "config.py").read_text(encoding="utf-8") == 'version = "v1.2.3"\n'


def test_remove_ok_requirements_only_inlines_folders_listed_in_deploy_txt(tmp_path, monkeypatch):
    copied_folders = []
    _write_repo_files(tmp_path, "src\nok\nrequirements.txt\n")
    monkeypatch.setattr(
        inline_ok_requirements,
        "find_and_copy_site_package",
        lambda folder, repo_dir: copied_folders.append(folder) or 0,
    )

    inline_ok_requirements.remove_ok_requirements(str(tmp_path), "v1.2.3")

    assert copied_folders == ["ok"]
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "pyappify==1.0.3\nrequests==2.32.3\n"
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

    assert copied_folders == ["pyappify"]
    assert (tmp_path / "requirements.txt").read_text(encoding="utf-8") == (
        "ok-script==1.0.147\nrequests==2.32.3\n"
    )
