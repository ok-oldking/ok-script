# Build the documentation website

[简体中文](../building-site.md) · [Documentation](index.md)

This repository uses [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) to generate a static HTML site from the Markdown under `docs/`. Site navigation, theme, and search are configured in `mkdocs.yml` at the repository root.

## Install documentation dependencies

Run from the repository root:

```powershell
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -m pip install -r requirements-docs.txt
```

## Preview locally

```powershell
& $py -m mkdocs serve
```

Open the local address shown in the terminal. The browser reloads as Markdown files change.

## Generate static HTML

```powershell
& $py -m mkdocs build --strict
```

The generated site is written to `site/`. It can be deployed to GitHub Pages, Cloudflare Pages, a static web server, or object storage.

`--strict` converts broken links, missing pages, and configuration warnings into build failures. Use it before submitting documentation changes.

## Add a page

1. Create a Markdown file under `docs/` or `docs/en/`.
2. Link pages and images with paths relative to the current file.
3. Add the page to `nav` in `mkdocs.yml`.
4. Maintain language-switch links on the Chinese and English entry pages.
5. Run a strict build and resolve every warning.

Static assets must live under `docs/`. Do not commit the generated `site/` directory.
