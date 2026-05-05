---
name: commit
description: Generate a commit message based on current changes and commit all staged and unstaged changes to git
---


# Commit Changes

When instructed to commit changes, follow these steps:

## 1. Check for uncommitted changes

// turbo
```powershell
git status --short
```

If there are no uncommitted changes (no output from the command above), tell the user "No uncommitted changes to commit." and **STOP**.

## 2. Review changes and generate a commit message

// turbo
```powershell
git diff --stat
```

// turbo
```powershell
git diff
```

Review the output of `git diff` and `git diff --stat`. Write a concise, descriptive commit message summarizing **only these uncommitted changes**. The message should:
- Use imperative mood (e.g. "Add …", "Fix …", "Refactor …")
- Be a single line for simple changes.
- For complex changes, use a single summary line, followed by a blank line and bullet points.

## 3. Stage and commit all changes

// turbo
```powershell
git add -A
```

// turbo
```powershell
git commit -m "<generated commit message>"
```

Replace `<generated commit message>` with the message you wrote in step 2.

## 4. Report

Tell the user:
- The commit message used.
- A brief summary of what was committed.

