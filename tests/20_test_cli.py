#!/usr/bin/env python

import pytest, two_cents
from test_helpers import *

def run_two_cents(argv='', *stdin):
    import io, shlex

    # Monkey-patch the functions that two_cents uses to interact with stdin and 
    # stdout.  This allows us to provide the input we want and to make sure 
    # that the correct messages are being printed.

    stdout = io.StringIO()
    stdin = list(stdin)

    def test_print(*args, **kwargs):
        print(*args, **kwargs)
        print(*args, file=stdout, **kwargs)

    def test_prompt(message, password=False):
        assert stdin
        response = stdin.pop(0)
        print(message, response)
        print(message, response, file=stdout)
        return response


    two_cents.cli.prompt = test_prompt
    two_cents.cli.print = test_print

    # Run two_cents in the cloistered test environment we've set up.
    
    two_cents.cli.main(shlex.split(argv), db_path=test_db_path)

    # Make sure that all of the input provided to stdin was used, and return 
    # the captured stdout.

    assert not stdin
    return stdout.getvalue()


def test_add_bank():
    factories = {
            'add-bank wells_fargo -u "echo username" -p "echo password"': [],
            'add-bank wells_fargo -u "echo username"': ['echo password'],
            'add-bank wells_fargo -p "echo password"': ['echo username'],
            'add-bank wells_fargo': ['echo username', 'echo password'],
    }

    for argv, stdin in factories.items():
        fresh_test_db()

        with open_test_db() as session:
            assert two_cents.get_num_banks(session) == 0

        run_two_cents(argv, *stdin)

        assert "Bank 'unsupported-bank' is not supported." in \
                run_two_cents('add-bank unsupported-bank')
        assert "Bank 'wells_fargo' already exists." in \
                run_two_cents('add-bank wells_fargo')

        with open_test_db() as session:
            bank = two_cents.get_bank(session, 'wells_fargo')
            assert bank.username_command == 'echo username'
            assert bank.password_command == 'echo password'
            assert bank.last_update == test_dates['today']

def test_add_budget(fresh_test_db):
    with open_test_db() as session:
        assert two_cents.get_num_budgets(session) == 0

    run_two_cents('add-budget apples')
    run_two_cents('add-budget bananas -b 100')
    run_two_cents('add-budget cherries -a "50 per year"')
    run_two_cents('add-budget peaches -b 30 -a "20 per month"')

    with open_test_db() as session:
        assert two_cents.get_num_budgets(session) == 4

        budget = two_cents.get_budget(session, 'apples')
        assert budget.balance == 0
        assert budget.allowance == 0
        assert budget.last_update == test_dates['today']

        budget = two_cents.get_budget(session, 'bananas')
        assert budget.balance == 100
        assert budget.allowance == 0
        assert budget.last_update == test_dates['today']

        budget = two_cents.get_budget(session, 'cherries')
        assert budget.balance == 0
        assert budget.allowance == approx(50 / 356)
        assert budget.last_update == test_dates['today']

        budget = two_cents.get_budget(session, 'peaches')
        assert budget.balance == 30
        assert budget.allowance == approx(20 * 12 / 356)
        assert budget.last_update == test_dates['today']

def test_reassign_payments(fresh_test_db):
    with open_test_db() as session:
        bank, payments, budgets = fill_database(session)
        payments[0].assign('groceries')
        assert two_cents.get_payment(session, 1).assignment == 'groceries'

    assert "No payment with id='42'." in \
            run_two_cents('reassign-payment 42 restaurants')
    assert "No payment with id='wrong-type'." in \
            run_two_cents('reassign-payment wrong-type restaurants')
    assert "No budget named 'no-such-budget'." in \
            run_two_cents('reassign-payment 1 no-such-budget')

    run_two_cents('reassign-payment 1 restaurants')

    with open_test_db() as session:
        assert two_cents.get_payment(session, 1).assignment == 'restaurants'

def test_show_payments(fresh_test_db):
    with open_test_db() as session:
        bank, payments, budgets = fill_database(session)
        payments[0].assign('groceries')
        payments[0].description = 'SAFEWAY'
        payments[1].description = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nam justo sem, malesuada ut ultricies ac, bibendum eu neque.'

    assert run_two_cents('show-payments') == '''\
Id: 1
Bank: Wells Fargo
Date: 01/01/14
Value: -$100.00
Assignment: groceries
Description: SAFEWAY

Id: 2
Bank: Wells Fargo
Date: 01/01/14
Value: -$10.00
Description:
  Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nam justo sem,
  malesuada ut ultricies ac, bibendum eu neque.

'''
    assert run_two_cents('show-payments groceries') == '''\
Id: 1
Bank: Wells Fargo
Date: 01/01/14
Value: -$100.00
Assignment: groceries
Description: SAFEWAY

'''

def test_transfer_money(fresh_test_db):
    with open_test_db() as session:
        fill_database(session)

    assert "Expected a dollar value, not 'infinity'." in run_two_cents(
            'transfer-money infinity groceries restaurants')
    assert "No budget named 'no-such-budget'." in run_two_cents(
            'transfer-money 100 groceries no-such-budget')
    assert "No budget named 'no-such-budget'." in run_two_cents(
            'transfer-money 100 no-such-budget restaurants')

    with open_test_db() as session:
        assert two_cents.get_budget(session, 'groceries').balance == 0
        assert two_cents.get_budget(session, 'restaurants').balance == 0

    run_two_cents('transfer-money 100 groceries restaurants')
    
    with open_test_db() as session:
        assert two_cents.get_budget(session, 'groceries').balance == -100
        assert two_cents.get_budget(session, 'restaurants').balance == 100

def test_update_budgets(fresh_test_db):
    assert "No budgets to display" in run_two_cents()

    with open_test_db() as session:
        fill_database(session)
        two_cents.get_budget(session, 'groceries').allowance = two_cents.parse_allowance('150 per month')
        two_cents.get_budget(session, 'restaurants').allowance = two_cents.parse_allowance('100 per month')

    run_two_cents('-D', 'groceries', 'restaurants')

    with open_test_db() as session:
        assert two_cents.get_num_unassigned_payments(session) == 0
        assert two_cents.get_payment(session, 1).assignment == 'groceries'
        assert two_cents.get_payment(session, 2).assignment == 'restaurants'

        add_payment(two_cents.get_bank(session, 'wells_fargo'), 150)

    run_two_cents('-D', 'groceries')

    with open_test_db() as session:
        assert two_cents.get_num_unassigned_payments(session) == 0
        assert two_cents.get_payment(session, 3).assignment == 'groceries'

        add_payment(two_cents.get_bank(session, 'wells_fargo'))

    run_two_cents('-D', 'skip')

    with open_test_db() as session:
        assert two_cents.get_num_unassigned_payments(session) == 1
        assert two_cents.get_payment(session, 4).assignment == None

    run_two_cents('-D', 'ignore')

    with open_test_db() as session:
        assert two_cents.get_num_unassigned_payments(session) == 0
        assert two_cents.get_payment(session, 4).assignment == 'ignore'

    assert run_two_cents('-D') == '''\
Groceries           $50.00         
Restaurants        -$10.00 (3 days)
'''

