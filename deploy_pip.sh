rm -r dist
rm -r build
python setup.py sdist bdist_wheel
twine upload dist/*