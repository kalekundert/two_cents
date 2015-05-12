import distutils.core

# Uploading to PyPI
# =================
# $ python setup.py register -r pypi
# $ python setup.py sdist upload -r pypi

version = '0.0'
distutils.core.setup(
        name='two_cents',
        version=version,
        author='Kale Kundert',
        url='https://github.com/username/two_cents',
        packages=['two_cents'],
        entry_points = {'console_scripts': ['two_cents=two_cents.cli:main']},
)
