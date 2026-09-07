import os
import setuptools

os.environ["PYTHONIOENCODING"] = "utf-8"

# Release builds provide an explicit version through the publish workflow.
# Local/isolated metadata builds must remain deterministic and offline-safe;
# querying PyPI from setup.py makes editable installs fail before dependency
# resolution and is not valid build-system behavior.
VERSION_NUM = os.environ.get('OK_SCRIPT_BUILD_VERSION', '2.0.7.dev0')
print(f'building version {VERSION_NUM}')

setuptools.setup(version=VERSION_NUM)
