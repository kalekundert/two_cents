#!/usr/bin/env python3

import testing
import sys, io
import budget, cli
from utilities import muffler
from contextlib import contextmanager

test_db = 'test.db'

def run_subcommand(arguments, 
        stdin=None, wipe=True, days_ago=None, months_ago=None, years_ago=None):

    import os, sys, datetime, shlex

    # Specify when the subcommand should pretend to run.
    today = datetime.date.today()
    fake_date = datetime.date.today()

    if years_ago:
        assert not days_ago and not months_ago
        fake_date = datetime.date(today.year - years_ago, 12, 31)

    if months_ago:
        assert not days_ago and not years_ago

        fake_month = today.month - months_ago
        fake_year = today.year

        while fake_month < 1:
            fake_month += 12
            fake_year -= 1

        fake_date = datetime.date(fake_year, fake_month, 1)

    if days_ago:
        assert not months_ago and not years_ago
        fake_date = today - datetime.timedelta(days_ago)

    try:
        # Setup an artificial environment to run the command in.
        budget.today = lambda: fake_date
        real_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
        if wipe: wipe_database()

        # Run the command.
        command = './cli.py --database {} {}'.format(test_db, arguments)
        print(command)
        sys.argv = shlex.split(command)
        cli.main()
        if stdin is not None: print(stdin, end='')

    finally:
        # Clean up the artificial environment.
        budget.today = lambda: datetime.date.today()
        sys.stdin = real_stdin

@contextmanager
def open_test_db():
    import os, os.path

    assert os.path.exists(test_db), \
            "The database '{}' was not successfully created.".format(test_db)

    with budget.open_db(test_db) as session:
        yield session

    assert os.path.exists(test_db), \
            "The database '{}' was unexpectedly destroyed".format(test_db)

    os.remove(test_db)

def wipe_database():
    import os
    with open(test_db, 'w'):
        os.utime(test_db, None)


@testing.test
def test_utility_functions():
    import datetime

    test_date = datetime.date(2014, 3, 5)
    assert budget.format_date(test_date) == '03/05/14'

    assert budget.format_value(3210) == '$32.10'
    assert budget.format_value(-3210) == '-$32.10'

    assert budget.to_cents('-32.10') == -3210
    assert budget.to_cents(32.10) == 3210

@testing.test
def test_add_account():

    # Make sure that no accounts can be found initially.

    wipe_database()

    with open_test_db() as session:
        assert budget.get_num_accounts(session) == 0

    # Create a new account without an allowance (command-line interface).

    run_subcommand('add groceries --savings')

    # Make sure the same account can't be created twice.

    with muffler.Muffler() as output:
        with testing.expect(SystemExit):
            run_subcommand('add groceries', wipe=False)
        assert "Account 'groceries' already exists." in output, output

    # Make sure all the right properties were saved.

    with open_test_db() as session:
        assert budget.account_exists(session, 'groceries')
        assert budget.get_num_accounts(session) == 1

        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')

        assert [account] == budget.get_accounts(session)
        assert account.name == 'groceries'
        assert account.value == 0

@testing.test
def test_add_account_allowances():

    # Forgo an allowance using the command-line interface.

    run_subcommand('add groceries --savings', days_ago=5)

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 0

    # Forgo an allowance using the interactive interface.

    run_subcommand('add groceries', days_ago=5, stdin='\n')

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 0

    # Create a daily allowance using the command-line interface.

    run_subcommand('add groceries --allowance 5 daily', days_ago=5)

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 2500

    # Create a daily allowance using the interactive interface.

    run_subcommand('add groceries', days_ago=5, stdin='5 daily\n')

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 2500

    # Create a monthly allowance.

    run_subcommand('add groceries --allowance 150 monthly', months_ago=2)

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 30000

    # Create a yearly allowance.

    run_subcommand('add groceries --allowance 100 yearly', years_ago=2)

    with open_test_db() as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 20000

@testing.test
def test_add_bank():

    # Make sure that no banks are found initially.

    wipe_database()

    with open_test_db() as session:
        assert budget.get_num_banks(session) == 0

    # Make sure the 'add-bank' subcommand works as expected.

    run_subcommand(
            'add-bank wells-fargo -u "echo username" -p "echo password"')

    with open_test_db() as session:
        assert budget.bank_exists(session, 'wells-fargo')
        assert budget.get_num_banks(session) == 1

        bank = budget.get_bank(session, 'wells-fargo')
        assert [bank] == budget.get_banks(session)
        assert bank.title == 'Wells Fargo'
        assert bank.username == 'username'
        assert bank.password == 'password'


def test_modify_account():
    pass

def test_modify_account_allowances():
    # Set an allowance, change it several times, and makes sure the account 
    # value is correct in the end.
    pass


if __name__ == '__main__':
    # coverage3 run tests.py
    # coverage3 html

    testing.title("Unit tests for budget manager")
    testing.run()


