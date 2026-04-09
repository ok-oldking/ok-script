---
name: deploy
description: Generate a commit message, commit all changes, run deploy_pip.ps1 to publish to PyPI, and tag HEAD with the deployed version on success
---

# Deploy to PyPI

When instructed to deploy, release, or publish to PyPI, follow these steps **in order**:

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

## 2. Run the deploy script using the virtual environment

// turbo
```powershell
.\.venv\Scripts\Activate.ps1; powershell -File ".\deploy_pip.ps1"
```

Wait for this to complete. **If the command fails (non-zero exit code or error output), STOP here and report the error to the user. Do NOT tag.**

## 3. Determine the deployed version

The deploy script calls `setup.py`, which increments the version. The version is printed in the output from `setup.py` as:

```
latest_version is X.Y.Z new version is X.Y.W
```

Search for "new version is" in the terminal output to find the exact version number (e.g., `1.0.98`).

## 4. Tag HEAD with the deployed version

// turbo
```powershell
git tag v<version>
```

Replace `<version>` with the version obtained in step 3 (e.g. `1.0.97`).

## 5. Push commit and tag

// turbo
```powershell
git push
```

// turbo
```powershell
git push --tags
```

## 6. Report

Tell the user:
- The commit message used (if any)
- The deployed version number
- That the tag has been pushed
