---
name: Deploy to PyPI
description: Generate a commit message, commit all changes, run deploy_pip.ps1 to publish to PyPI, and tag HEAD with the deployed version on success
---

# Deploy to PyPI

When instructed to deploy, release, or publish to PyPI, follow these steps **in order**:

## 1. Review changes and generate a commit message

// turbo
```powershell
git -C "d:\projects\ok-script" diff --stat
```

// turbo
```powershell
git -C "d:\projects\ok-script" diff
```

Review the output of `git diff` and `git diff --stat`. Write a concise, descriptive commit message summarising **all** staged and unstaged changes. The message should:
- Use imperative mood (e.g. "Add …", "Fix …", "Refactor …")
- Be a single line unless the changes are complex, in which case add a blank line followed by bullet points

## 2. Stage and commit all changes

```powershell
git -C "d:\projects\ok-script" add -A
```

```powershell
git -C "d:\projects\ok-script" commit -m "<generated commit message>"
```

Replace `<generated commit message>` with the message you wrote in step 1.

## 3. Run the deploy script

```powershell
powershell -File "d:\projects\ok-script\deploy_pip.ps1"
```

Wait for this to complete. **If the command fails (non-zero exit code or error output), STOP here and report the error to the user. Do NOT tag.**

## 4. Determine the deployed version

The deploy script calls `setup.py`, which auto-increments the patch version from the latest PyPI release. The version is printed in the build output as:

```
latest_version is X.Y.Z new version is X.Y.W
```

Parse the **new version** (`X.Y.W`) from the build output.

## 5. Tag HEAD with the deployed version

```powershell
git -C "d:\projects\ok-script" tag v<version>
```

Replace `<version>` with the version obtained in step 4 (e.g. `v1.0.97`).

## 6. Push commit and tag

```powershell
git -C "d:\projects\ok-script" push
```

```powershell
git -C "d:\projects\ok-script" push --tags
```

## 7. Report

Tell the user:
- The commit message used
- The deployed version number
- That the tag has been pushed
