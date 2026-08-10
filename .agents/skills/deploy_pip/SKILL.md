---
name: deploy
description: Create and push a version tag to publish to PyPI and create a GitHub Release through GitHub Actions
---

# Deploy to PyPI

When instructed to deploy, release, or publish to PyPI, follow these steps **in order**. GitHub Actions builds the tagged commit, publishes it with the repository's `PYPI_API_TOKEN` secret, and creates the GitHub Release.

## 1. Check for uncommitted changes and commit if necessary

// turbo
```powershell
git status --short
```

If there are uncommitted changes:
1. Run `git diff --stat` and `git diff` to review them.
// turbo
```powershell
git diff --stat
```
// turbo
```powershell
git diff
```
2. Write a concise, descriptive commit message summarizing **only these uncommitted changes**.
3. Stage and commit:
// turbo
   ```powershell
   git add -A
   ```
// turbo
   ```powershell
   git commit -m "<generated commit message>"
   ```
If there are NO uncommitted changes, proceed directly to Step 2.

## 2. Determine the release version

Choose the exact package version to release (for example, `1.0.98`). The Git tag must be `v<version>`, and the workflow passes `<version>` to the build through `OK_SCRIPT_BUILD_VERSION`.

## 3. Tag HEAD with the release version

// turbo
```powershell
git tag v<version>
```

Replace `<version>` with the chosen version (e.g. `1.0.98`).

## 4. Push commit and tag

// turbo
```powershell
git push --tags
```

## 5. Verify the workflow

Open the GitHub Actions run triggered by the pushed tag. It must complete both the `Build and publish` and `Create GitHub release` jobs. If publishing fails, do not create or move another tag; report the failure.

## 6. Report

Tell the user:
- The commit message used (if any)
- The release version and tag
- That the tag has been pushed and the GitHub Actions run result
