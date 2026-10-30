"""Plugin entry points and release downloads; no UI toolkit dependencies."""

import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from ok.core.script_packager import MAX_ARCHIVE_SIZE, inspect_script_archive
from ok.util.version import compare_versions

PLUGIN_SOURCE_FILE = '.ok-plugin-source.json'


def import_plugin_class(folder, entry):
    """Isolate declared entry modules while allowing package-relative imports."""
    folder = str(Path(folder).resolve())
    namespace = '_ok_plugin_' + hashlib.sha256(folder.encode()).hexdigest()[:16]
    if namespace not in sys.modules:
        package = types.ModuleType(namespace)
        package.__path__ = [folder]
        sys.modules[namespace] = package
    module = importlib.import_module(f'{namespace}.{entry[0]}')
    return getattr(module, entry[1])


def forget_plugin_modules(folder):
    folder = Path(folder).resolve()
    namespace = '_ok_plugin_' + hashlib.sha256(str(folder).encode()).hexdigest()[:16]
    for name, module in tuple(sys.modules.items()):
        source = getattr(module, '__file__', None)
        if (name == namespace or name.startswith(namespace + '.')
                or source and Path(source).resolve().is_relative_to(folder)):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


def github_repository(value):
    value = value.strip().rstrip('/')
    if '://' not in value:
        value = 'https://github.com/' + value
    parsed = urlparse(value)
    parts = parsed.path.strip('/').split('/')
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com'
            or len(parts) != 2 or any(not part or part in {'.', '..'} for part in parts)
            or parsed.query or parsed.fragment):
        raise ValueError('Enter a GitHub repository URL or owner/repository')
    owner, repository = parts
    repository = repository.removesuffix('.git')
    if not repository or any(not (c.isalnum() or c in '-_.') for c in owner + repository):
        raise ValueError('Invalid GitHub repository')
    return owner, repository


def github_release_assets(repository, session=None):
    """Find uploaded plugin archives, preferring a stable published release."""
    owner, name = github_repository(repository)
    client = session or requests
    response = client.get(
        f'https://api.github.com/repos/{owner}/{name}/releases',
        params={'per_page': 20}, headers={'Accept': 'application/vnd.github+json'}, timeout=(10, 30),
    )
    response.raise_for_status()
    releases = response.json()
    if not isinstance(releases, list):
        raise ValueError('GitHub did not return a release list')
    candidates = []
    for release in releases:
        if release.get('draft'):
            continue
        assets = []
        for asset in release.get('assets', []):
            filename = asset.get('name', '')
            if not filename.lower().endswith(('.okscript', '.zip')):
                continue
            if asset.get('size', 0) > MAX_ARCHIVE_SIZE:
                continue
            assets.append({
                'name': filename,
                'url': asset['browser_download_url'],
                'tag': release.get('tag_name', ''),
                'repository': f'{owner}/{name}',
            })
        if assets:
            assets.sort(key=lambda asset: (not asset['name'].lower().endswith('.okscript'), asset['name']))
            candidates.append((bool(release.get('prerelease')), assets))
    if not candidates:
        raise ValueError('No .zip or .okscript release assets found in this repository')
    return next((assets for prerelease, assets in candidates if not prerelease), candidates[0][1])


@dataclass
class PreparedPlugin:
    path: str
    manifest: dict
    temporary: object = None
    source: dict | None = None

    def close(self):
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None


def prepare_local_plugin(path):
    return PreparedPlugin(os.fspath(path), inspect_script_archive(path))


def github_asset_source(asset):
    repository = asset.get('repository') or '/'.join(urlparse(asset['url']).path.strip('/').split('/')[:2])
    owner, name = github_repository(repository)
    return {'repository': f'{owner}/{name}', 'tag': asset.get('tag', ''), 'asset_name': asset['name']}


def read_plugin_source(folder):
    try:
        source = json.loads((Path(folder) / PLUGIN_SOURCE_FILE).read_text(encoding='utf-8'))
        owner, name = github_repository(source['repository'])
        if not all(isinstance(source.get(key, ''), str) for key in ('tag', 'asset_name')):
            return None
        return {**source, 'repository': f'{owner}/{name}'}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def write_plugin_source(folder, source):
    path = Path(folder) / PLUGIN_SOURCE_FILE
    if source is None:
        # A locally installed archive does not inherit a previous repository,
        # or repository metadata supplied by the package itself.
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps(source, indent=2), encoding='utf-8')


def newer_plugin_version(candidate, installed):
    try:
        return compare_versions(candidate, installed) > 0
    except ValueError as error:
        raise ValueError(f'Cannot compare plugin versions: {installed!r}, {candidate!r}') from error


def plugin_update_assets(entry, session=None):
    source = read_plugin_source(entry['folder'])
    if source is None:
        return []
    assets = github_release_assets(source['repository'], session)
    installed = entry.get('version') or source['tag']
    return [asset for asset in assets if newer_plugin_version(asset['tag'], installed)]


def download_plugin(asset, session=None):
    client = session or requests
    url = asset['url']
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com':
        raise ValueError('Invalid GitHub release download URL')
    temporary = tempfile.TemporaryDirectory(prefix='ok-plugin-')
    path = Path(temporary.name) / ('plugin' + Path(asset['name']).suffix.lower())
    try:
        with client.get(url, stream=True, timeout=(10, 30)) as response:
            response.raise_for_status()
            if int(response.headers.get('Content-Length', 0)) > MAX_ARCHIVE_SIZE:
                raise ValueError('Plugin download is too large')
            size = 0
            with path.open('wb') as output:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_SIZE:
                        raise ValueError('Plugin download is too large')
                    output.write(chunk)
        return PreparedPlugin(str(path), inspect_script_archive(path), temporary, github_asset_source(asset))
    except Exception:
        temporary.cleanup()
        raise
