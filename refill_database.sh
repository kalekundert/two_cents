#!/usr/bin/env sh

./budget add-bank WellsFargo        \
    -u 'abraxas -Nq wells-fargo'    \
    -p 'abraxas -Pq wells-fargo'
./budget add-budget groceries
./budget add-budget restaurants
./budget add-budget miscellaneous

