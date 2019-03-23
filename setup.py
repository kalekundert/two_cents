#!/usr/bin/env python3
# encoding: utf-8

from setuptools import setup

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
    description="A program to help you manage your budget.",
    long_description=readme,
    url='https://github.com/kalekundert/two_cents',
    packages=[
        'two_cents',
    ],
    entry_points = {
        'console_scripts': ['two_cents_daemon=two_cents.daemon:main'],
    },
    include_package_data=True,
    install_requires=[
        'django',
        'djangorestframework',
        'django-model-utils',
        'plaid-python',
    ],
    zip_safe=False,
    keywords=[
        'two_cents',
    ],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
    ],
)
