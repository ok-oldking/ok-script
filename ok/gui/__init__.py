"""Compatibility namespace for the Qt UI moved to :mod:`ok.ui.qt`.

New code should import ``ok.ui.qt``. Existing ``ok.gui`` imports are redirected
to the same module objects so classes are not defined twice under the legacy
and current package names.
"""

from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.util import find_spec, spec_from_loader
from pathlib import Path
import sys


class _QtAliasLoader(Loader):
    def __init__(self, alias_name, target_name):
        self.alias_name = alias_name
        self.target_name = target_name

    def create_module(self, spec):
        return import_module(self.target_name)

    def exec_module(self, module):
        sys.modules[self.alias_name] = module


class _QtAliasFinder(MetaPathFinder):
    legacy_prefix = f"{__name__}."
    current_prefix = "ok.ui.qt."

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.legacy_prefix):
            return None
        target_name = self.current_prefix + fullname[len(self.legacy_prefix):]
        target_spec = find_spec(target_name)
        if target_spec is None:
            return None
        return spec_from_loader(
            fullname,
            _QtAliasLoader(fullname, target_name),
            origin=target_spec.origin,
            is_package=target_spec.submodule_search_locations is not None,
        )


if not any(isinstance(finder, _QtAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _QtAliasFinder())

_compat = Path(__file__).resolve().parent
__path__ = [str(_compat), str(_compat.parent / "ui" / "qt")]
