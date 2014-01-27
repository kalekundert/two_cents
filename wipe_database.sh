#!/usr/bin/env sh

rm -f ~/.config/budget/budget.db

./main.py add-bank wells-fargo
./main.py add-account grocery
./main.py add-account restaurant
./main.py add-account miscellaneous
