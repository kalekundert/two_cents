#!/usr/bin/env sh

./cli.py add-bank wells-fargo       \
    -u 'abraxas -Nq wells-fargo'    \
    -p 'abraxas -Pq wells-fargo'
./cli.py add groceries
./cli.py add restaurants
./cli.py add miscellaneous

