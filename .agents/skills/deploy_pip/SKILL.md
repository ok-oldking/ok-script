---
name: deploy pip
description: Generate a commit message, commit all changes, run deploy_pip.ps1 to publish to PyPI, and tag HEAD with the deployed version on success
---

# Deploy to PyPI

When instructed to deploy, release, or publish to PyPI, follow these steps **in order**:

## 1. Review changes and generate a commit message

// turbo
```powershell
git diff --stat
```

// turbo
```powershell
git diff
```

Review the output of `git diff` and `git diff --stat`. Write a concise, descriptive commit message summarising **all** staged and unstaged changes. The message should:
- Use imperative mood (e.g. "Add …", "Fix …", "Refactor …")
- Be a single line unless the changes are complex, in which case add a blank line followed by bullet points

## 2. Stage and commit all changes

```powershell
git add -A
```

```powershell
git commit -m "<generated commit message>"
```

Replace `<generated commit message>` with the message you wrote in step 1.

## 3. Run the deploy script using the virtual environment

// turbo
```powershell
.\.venv\Scripts\Activate.ps1; powershell -File ".\deploy_pip.ps1"
```

Wait for this to complete. **If the command fails (non-zero exit code or error output), STOP here and report the error to the user. Do NOT tag.**

## 4. Determine the deployed version

The deploy script calls `setup.py`, which increments the version. The version is printed in the output from `setup.py` as:

```
latest_version is X.Y.Z new version is X.Y.W
```

Search for "new version is" in the terminal output to find the exact version number (e.g., `1.0.98`).

## 5. Tag HEAD with the deployed version

```powershell
git tag v<version>
```

Replace `<version>` with the version obtained in step 4 (e.g. `1.0.97`).

## 6. Push commit and tag

```powershell
git push
```

```powershell
git push --tags
```

## 7. Report

Tell the user:
- The commit message used
- The deployed version number
- That the tag has been pushed
