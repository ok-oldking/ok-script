import os
import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

MODULE_NAME = "ok-script"

VERSION_NUM = os.environ.get("OK_SCRIPT_VERSION")
if not VERSION_NUM:
    raise RuntimeError("OK_SCRIPT_VERSION is required for build")

setuptools.setup(
    name=MODULE_NAME,
    version=VERSION_NUM,
    author="alicejump",
    author_email="149395013+AliceJump@users.noreply.github.com",
    description="Automation with Computer Vision for Python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/alicejump/ok-script",
    packages=setuptools.find_packages(exclude=["tests", "docs"]),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ],
    install_requires=[
        "pywin32>=306",
        "pyappify>=1.0.2",
        "PySide6-Fluent-Widgets==1.8.3",
        "typing-extensions>=4.11.0",
        "requests>=2.32.3",
        "psutil>=6.0.0",
        "pydirectinput==1.0.4",
        "pycaw==20240210",
        "mouse==0.7.1",
    ],
    python_requires="==3.12.*",
    zip_safe=False,
)
