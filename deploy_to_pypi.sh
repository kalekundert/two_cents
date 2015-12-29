#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

if [ "$#" != 1 ]; then 
    echo "Usage: ./deploy_to_pypi.sh <major|minor|patch>"
    exit 1
fi

git pull
bumpversion $1
git push && git push --tags
python setup.py sdist upload

