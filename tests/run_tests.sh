#!/usr/bin/env sh

if [ $# -gt 0 ]; then
    py.test --cov two_cents $@
else
    py.test --cov two_cents model_tests.py cli_tests.py
fi
coverage html
