RD /S /Q dist
RD /S /Q build
python setup.py sdist bdist_wheel
twine upload dist/*