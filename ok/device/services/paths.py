"""Open a local path with the platform's default application."""

import os
from pathlib import Path
import subprocess
import sys


def open_path(path):
    """Open an existing local file/folder; never interpret shell text or URLs."""
    resolved = Path(path).resolve(strict=True)
    if sys.platform == 'win32':
        os.startfile(str(resolved))
    elif sys.platform == 'darwin':
        subprocess.run(['/usr/bin/open', str(resolved)], check=True, timeout=5)
    else:
        raise NotImplementedError('Local path opening is unavailable on this platform')
