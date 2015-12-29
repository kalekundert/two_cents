#!/usr/bin/env python3
# encoding: utf-8

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import re
with open('two_cents/__init__.py') as file:
    version_pattern = re.compile("__version__ = '(.*)'")
    version = version_pattern.search(file.read()).group(1)

with open('README.rst') as file:
    readme = file.read()

setup(
    name='two_cents',
    version=version,
    author='Kale Kundert',
    author_email='kale@thekunderts.net',
    description='',
    long_description=readme,
    url='https://github.com/kalekundert/two_cents',
    packages=[
        'two_cents',
    ],
    entry_points = {
        'console_scripts': ['two_cents=two_cents.cli:main'],
    },
    include_package_data=True,
    install_requires=[
        'SQLAlchemy',
        'selenium',
        'xvfbwrapper',
        'ofxparse',
        'docopt==0.6.2',
        'appdirs',
        'prettytable',
    ],
    zip_safe=False,
    keywords=[
        'two_cents',
    ],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)
