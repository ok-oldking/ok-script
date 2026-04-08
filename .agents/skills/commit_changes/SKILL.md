---
name: commit
description: Generate a commit message based on current changes and commit all staged and unstaged changes to git
---


# Commit Changes

When instructed to commit changes, follow these steps:

## 1. Review changes and generate a commit message

// turbo
```powershell
git diff --stat
```

// turbo
```powershell
git diff
```

Review the output of `git diff` and `git diff --stat`. Write a concise, descriptive commit message summarizing **all** changes. The message should:
- Use imperative mood (e.g. "Add …", "Fix …", "Refactor …")
- Be a single line for simple changes.
- For complex changes, use a single summary line, followed by a blank line and bullet points.

## 2. Stage and commit all changes

```powershell
git add -A
```

```powershell
git commit -m "<generated commit message>"
```

Replace `<generated commit message>` with the message you wrote in step 1.

## 3. Report

Tell the user:
- The commit message used.
- A brief summary of what was committed.
