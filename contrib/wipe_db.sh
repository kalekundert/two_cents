mysql -p <<EOF
drop database if exists two_cents;
create database if not exists two_cents;
EOF

../manage.py migrate
../manage.py createsuperuser


