#!/usr/bin/env python3

import testing
import sys, io
import budget, cli
from utilities import muffler
from contextlib import contextmanager

test_db = 'test.db'

def run_subcommand(arguments, stdin=None, wipe=True, **kwargs):
    import os, sys, shlex
    try:
        # Setup an artificial environment to run the command in.
        real_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
        if wipe: wipe_database()

        # Run the command.
        command = './cli.py --database {} {}'.format(test_db, arguments)
        print(command)
        sys.argv = shlex.split(command)
        with change_date(**kwargs): cli.main()
        if stdin is not None: print(stdin, end='')

    finally:
        # Clean up the artificial environment.
        sys.stdin = real_stdin

@contextmanager
def open_test_db(**kwargs):
    import os, os.path

    assert os.path.exists(test_db), \
            "The database '{}' was not successfully created.".format(test_db)

    with change_date(**kwargs):
        with budget.open_db(test_db) as session:
            yield session

    assert os.path.exists(test_db), \
            "The database '{}' was unexpectedly destroyed".format(test_db)

@contextmanager
def change_date(days_ago=None, months_ago=None, years_ago=None):
    import datetime

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

    budget.today = lambda: fake_date
    yield
    budget.today = lambda: datetime.date.today()

@testing.setup
def wipe_database():
    import os
    with open(test_db, 'w'):
        os.utime(test_db, None)

@testing.teardown
def remove_database():
    import os
    if os.path.exists(test_db):
        os.remove(test_db)


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

    # Create several allowances at once.

    run_subcommand('add groceries --allowance 3 daily', days_ago=10)
    run_subcommand('add restaurants --allowance 2 daily', days_ago=10, wipe=False)
    run_subcommand('add miscellaneous --allowance 1 daily', days_ago=10, wipe=False)

    with open_test_db() as session:
        budget.update_accounts(session)

        groceries = budget.get_account(session, 'groceries')
        restaurants = budget.get_account(session, 'restaurants')
        miscellaneous = budget.get_account(session, 'miscellaneous')

        assert groceries.value == 3000
        assert restaurants.value == 2000
        assert miscellaneous.value == 1000

@testing.test
def test_add_bank():

    # Make sure that no banks are found initially.

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

@testing.test
def test_modify_account_allowances():
    # Setup an initial allowance.  Make a few extra accounts to confuse things.

    run_subcommand('add groceries --allowance 3 daily', days_ago=40)

    with open_test_db(days_ago=30) as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 3000

    # Test modifying the allowance.

    run_subcommand(
            'modify-allowance groceries --allowance 2 daily',
            days_ago=30, wipe=False)

    with open_test_db(days_ago=20) as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 5000

    # Test modifying the allowance again.

    run_subcommand(
            'modify-allowance groceries --allowance 1 daily',
            days_ago=20, wipe=False)

    with open_test_db(days_ago=10) as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        assert account.value == 6000

    # Test turning off the allowance altogether.

    run_subcommand(
            'modify-allowance groceries --savings',
            days_ago=10, wipe=False)

    with open_test_db(days_ago=0) as session:
        budget.update_accounts(session)
        account = budget.get_account(session, 'groceries')
        print(account.value)
        assert account.value == 6000


if __name__ == '__main__':
    # coverage3 run tests.py
    # coverage3 html

    testing.title("Unit tests for budget manager")
    testing.run()


