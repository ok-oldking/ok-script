import os

import setuptools
from Cython.Build import cythonize
from distutils.extension import Extension

os.environ["PYTHONIOENCODING"] = "utf-8"
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
from setuptools import setup, Extension
from Cython.Build import cythonize
import sys
from get_pypi_latest_version import GetPyPiLatestVersion

MODULE_NAME = "ok-script"

obtainer = GetPyPiLatestVersion()
try:
    latest_version = obtainer(MODULE_NAME)
except Exception as e:
    latest_version = "0.0.0"
VERSION_NUM = obtainer.version_add_one(latest_version, add_patch=True)
print(f'latest_version is {latest_version} new version is {VERSION_NUM}')

# Check if the build command includes --inplace
if '--inplace' in sys.argv:
    compiler_directives = {
        'language_level': "3",
        'linetrace': False,
        'embedsignature': False,
        'binding': False,
        'profile': False,
    }
else:
    compiler_directives = {
        'language_level': "3",
        'linetrace': False,
        'embedsignature': False,
        'binding': False,
        'profile': False,
    }
compiler_directives = {
    'language_level': "3",
}

def find_pyx_packages(base_dir):
    extensions = []
    for dirpath, _, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename.endswith(".pyx"):
                module_path = os.path.join(dirpath, filename).replace('/', '.').replace('\\', '.')
                module_name = module_path[:-4]  # Remove the .pyx extension
                extensions.append(
                    Extension(name=module_name, language="c++", sources=[os.path.join(dirpath, filename)]))
                print(f'add Extension: {module_name} {[os.path.join(dirpath, filename)]}')
    return extensions


base_dir = "ok"
extensions = find_pyx_packages(base_dir)

setuptools.setup(
    name=MODULE_NAME,
    version=VERSION_NUM,
    author="ok-oldking",
    author_email="firedcto@gmail.com",
    description="Automation with Computer Vision for Python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ok-oldking/ok-script",
    packages=setuptools.find_packages(exclude=['tests', 'docs']),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ],
    install_requires=[
        'pywin32>=306',
        'pyappify>=1.0.2',
        'PySide6-Fluent-Widgets==1.8.3',
        'typing-extensions>=4.11.0',
        'requests>=2.32.3',
        'psutil>=6.0.0',
        'pydirectinput==1.0.4',
        'pycaw==20240210',
        'mouse==0.7.1'
    ],
    python_requires='==3.12.*',
    ext_modules=cythonize(extensions, compiler_directives=compiler_directives),
    zip_safe=False,
)
