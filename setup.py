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
        install_requires=[
            'SQLAlchemy==1.0.4',
            'docopt==0.6.2',
            'ofxparse==0.14',
            'selenium',
            'pytest==2.7.0',
            'pytest-cov==1.8.1',
        ],
        entry_points = {
            'console_scripts': ['two_cents=two_cents.cli:main'],
        },
)
