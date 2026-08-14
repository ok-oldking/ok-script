# 构建文档网站

[English](en/building-site.md) · [文档中心](index.md)

本仓库使用 [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) 将 `docs/` 下的 Markdown 生成静态 HTML 网站。站点导航、主题和搜索配置位于仓库根目录的 `mkdocs.yml`。

## 安装文档依赖

在仓库根目录执行：

```powershell
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
& $py -m pip install -r requirements-docs.txt
```

## 本地预览

```powershell
& $py -m mkdocs serve
```

打开终端显示的本地地址。修改 Markdown 后，浏览器会自动刷新。

## 生成静态 HTML

```powershell
& $py -m mkdocs build --strict
```

生成结果位于 `site/` 目录。该目录可以部署到 GitHub Pages、Cloudflare Pages、静态 Web 服务器或对象存储。

`--strict` 会把无效链接、缺失页面和配置警告当作构建失败，建议在提交文档前始终使用。

## 添加页面

1. 在 `docs/` 或 `docs/en/` 下创建 Markdown 文件。
2. 使用相对于当前文件的链接引用其他页面和图片。
3. 在 `mkdocs.yml` 的 `nav` 中加入页面。
4. 同时维护中文和英文入口的语言切换链接。
5. 运行严格构建，确认站点无警告。

图片等静态资源必须放在 `docs/` 内。不要提交生成的 `site/` 目录。
