Two Cents
=========
Two Cents is a continuously (rather than monthly) updating budget program.  So 
instead of saying "You have $500 to spend on groceries in April", Two Cents 
either says "You are over your grocery budget right now, try not to spend more 
than you have to" or "You are within your grocery budget, go ahead and make a 
nice dinner".  In this way Two Cents directly tells you whether or not it's OK 
to splurge at the moment, which is often all you need to know.

Each budget can have an allowance, which would be something like ``$500/mo``.  
Every time you run ``two_cents``, it will calculate how many seconds have 
elapsed since you called it and apply allowances for each budget accordingly.  
It will also download recent activity from your bank, ask you to assign 
transactions to budgets, and credit or debit your budgets accordingly.  
Finally, it will display the balance for each budget.  For budgets with 
negative balances, it will also display an estimate for how long it will take 
for the budget to return to the black.

.. image:: https://img.shields.io/pypi/v/two_cents.svg
   :target: https://pypi.python.org/pypi/two_cents

.. image:: https://img.shields.io/pypi/pyversions/two_cents.svg
   :target: https://pypi.python.org/pypi/two_cents

.. image:: https://travis-ci.org/kalekundert/two_cents.svg?branch=master
   :target: https://travis-ci.org/kalekundert/two_cents

.. image:: https://coveralls.io/repos/github/kalekundert/two_cents/badge.svg?branch=master
   :target: https://coveralls.io/github/kalekundert/two_cents?branch=master


Deployment
----------
Install Two Cents from PyPI:

   pip install two_cents

Specify the configuration options specific to your deployment in a python 
script conventionally named ``site_settings.py``.  This script has the same 
syntax as the regular Django ``settings.py`` file.  The following values must 
be specified::

   SECRET_KEY = ...

   DATABASES['default']['NAME'] = ...
   DATABASES['default']['USER'] = ...
   DATABASES['default']['PASSWORD'] = ...
   DATABASES['default']['HOST'] = ...
   DATABASES['default']['PORT'] = ...

   PLAID_CLIENT_ID = ...
   PLAID_SECRET = ...
   PLAID_PUBLIC_KEY = ...
   PLAID_ENVIRONMENT = ...

The ``SECRET_KEY`` is used by Django to sign various things, and should be 
long, unique, and secret.  The following snippet (from `Stack Overflow`__) is a 
simple way to generate a new key::

   import os, binascii
   binascii.hexlify(os.urandom(32)) 

__ https://stackoverflow.com/questions/34897740/whats-the-simplest-and-safest-method-to-generate-a-api-key-and-secret-in-python

Note that Two Cents is tested with MariaDB (e.g. MySQL), so that is the default 
database backend.  Other backends may also work, but are not supported.  Any 
other option understood by Django can be specified as well.  Options specified 
in this file will override the built-in Two Cents settings, although this 
should rarely be necessary.

Specify the path to the above ``site_settings.py`` file in an environment 
variable called ``$TWO_CENTS_SITE_SETTINGS``::

   $ export TWO_CENTS_SITE_SETTINGS=/path/to/site_settings.py

Finally, launch website using the WSGI server of you choice::

   $ gunicorn two_cents.wsgi

Basic Usage
-----------
The first step is to tell Two Cents about your bank.  Currently only Wells 
Fargo is supported::

   $ two_cents add_bank wells_fargo

Two Cents will ask for commands it can run to generate your username and 
password.  It needs this information so it can log into your account and scrape 
your most recent activity.  Your login information is stored locally and is 
never sent to any site other than your bank.  If you don't mind storing your 
password in plaintext, use the echo command::

   Username: echo "alice"
   Password: echo "pa55w0rd"

Otherwise, provide a command like ``gpg`` or ``gnome-keyring`` that can store 
your password encrypted and can unencrypt it for Two Cents.

Once you've added your bank, the next step is to add one or more budgets::

   $ two_cents add_budget groceries -a 500/mo
   $ two_cents add_budget restaurants -a 200/mo
   $ two_cents add_budget miscellaneous -a 100/mo

The ``-a`` option sets the allowance for the new budget.  You can also leave 
off this argument and set (or change) the allowance later.  There is also an 
option to set the initial balance for the new budget, but the default ($0) is 
usually what you want.

Once you've configured your bank and your budgets, you can run ``two_cents`` 
with no arguments to see the status of your budgets::

   $ two_cents
   
If any new transactions are found from your bank, you will be asked to assign 
them to a budget.  If a budget has a positive balance, you should feel 
comfortable spending from it.  If a budget has a negative balance, you should 
try not to spend from it for a while.  Two Cents will tell you how long it will 
take the budget to return to a positive balance assuming no further spending.

Downloading Transactions via Cron
---------------------------------
It can take a while for Two Cents to connect to your bank and download new 
transactions.  If you want to save yourself some time, you can use ``cron`` to 
download new transactions in the background every hour or so::

   $ crontab -e
   0 * * * * two_cents download_payments -I

The ``-I`` command prevents Two Cents from expecting any input on stdin.  You 
also need to ensure that the username and password commands you provided will 
work without your input.  For example, if you used ``gpg``, you will need to 
run an agent with your unlocked private key.

Once your account activity is being downloaded in the background, write a 
simple shell function that will call Two Cents with the ``-D`` option unless 
any other options are specified.  The ``-D`` option tells Two Cents to not 
download new activity::

   $ vim ~/.bashrc
   function two_cents () {
       if [ $# = 0 ]; then
           command two_cents -D
       else
           command two_cents $@
       fi
   }

(I know it'd probably be better to have a configuration file, but for the time 
being this is the best way to do this.)

