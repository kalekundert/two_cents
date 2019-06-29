#!/usr/bin/env sh
set -euo pipefail

cd $(dirname $0)/..

echo "Logging in to MySQL:"
mysql -p <<EOF
drop database if exists two_cents;
create database if not exists two_cents;
EOF

rm two_cents/migrations/*.py
touch two_cents/migrations/__init__.py
./manage.py makemigrations
./manage.py migrate

echo
echo "Creating website admin:"
./manage.py createsuperuser     \
  --username kale               \
  --email kale@thekunderts.net  \
