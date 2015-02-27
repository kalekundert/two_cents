#!/usr/bin/env sh

./wipe_database.sh

./twocents add-bank wells_fargo       \
    -u 'abraxas -Nq wells-fargo'    \
    -p 'abraxas -Pq wells-fargo'

./twocents add-budget groceries -a '$150 per month'
./twocents add-budget restaurants -a '$100 per month'
./twocents add-budget miscellaneous -a '$100 per month'

