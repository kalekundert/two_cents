#!/usr/bin/env python3

import pytest, two_cents
from test_helpers import *

def test_open_db(fresh_test_db):
    try:
        with open_test_db() as session:
            assert two_cents.get_num_banks(session) == 0
            assert two_cents.get_num_budgets(session) == 0

            fill_database(session)

            assert two_cents.get_num_banks(session) == 1
            assert two_cents.get_num_budgets(session) == 2

            # Raise an exception to see if the database session is correctly 
            # rolled back.

            raise ZeroDivisionError

    except ZeroDivisionError:
        pass

    with open_test_db() as session:
        assert two_cents.get_num_banks(session) == 0
        assert two_cents.get_num_budgets(session) == 0

def test_budget_schema(fresh_test_db):
    with open_test_db() as session:
        assert two_cents.get_budgets(session) == []
        assert two_cents.get_num_budgets(session) == 0
        assert not two_cents.budget_exists(session, 'groceries')
        assert not two_cents.budget_exists(session, 'restaurants')

        with pytest.raises(two_cents.NoSuchBudget):
            assert two_cents.get_budget(session, 'groceries')
        with pytest.raises(two_cents.NoSuchBudget):
            assert two_cents.get_budget(session, 'restaurants')

        bank, payments, budgets = fill_database(session)
        budgets[1].balance = 0
        budgets[1].balance = -100

        assert two_cents.get_num_budgets(session) == 2
        assert two_cents.get_budgets(session) == budgets
        assert two_cents.get_budget(session, 'groceries') is budgets[0]
        assert two_cents.get_budget(session, 'restaurants') is budgets[1]
        assert two_cents.budget_exists(session, 'groceries')
        assert two_cents.budget_exists(session, 'restaurants')
        assert budgets[0].recovery_time == 0
        assert budgets[1].recovery_time == -1

        with pytest.raises(two_cents.UserError):
            add_budget(session, 'skip')
        with pytest.raises(two_cents.UserError):
            add_budget(session, 'ignore')

        budgets[0].allowance = two_cents.parse_allowance('150 per month')
        budgets[1].allowance = two_cents.parse_allowance('100 per month')

        assert budgets[0].recovery_time == 0
        assert budgets[1].recovery_time == 30

        change_date('next month')
        two_cents.update_allowances(session)

        # All the numbers in these 6 assertions were checked by hand.

        assert budgets[0].balance == approx(150 * 31 * 12 / 356)
        assert budgets[0].pretty_balance == '$156.74'
        assert budgets[0].recovery_time == 0
        assert budgets[1].balance == approx(100 * 31 * 12 / 356 - 100)
        assert budgets[1].pretty_balance == '$4.49'
        assert budgets[1].recovery_time == 0

def test_payment_schema(fresh_test_db):
    with open_test_db() as session:
        assert two_cents.get_payments(session) == []
        assert two_cents.get_unassigned_payments(session) == []
        assert two_cents.get_num_unassigned_payments(session) == 0

        with pytest.raises(two_cents.NoSuchPayment):
            assert two_cents.get_payment(session, 1) is None
        with pytest.raises(two_cents.NoSuchPayment):
            assert two_cents.get_payment(session, 2) is None

        bank, payments, budgets = fill_database(session)
        groceries, restaurants = budgets

        assert two_cents.get_payments(session) == payments
        assert two_cents.get_unassigned_payments(session) == payments
        assert two_cents.get_num_unassigned_payments(session) == 2
        assert two_cents.get_payment(session, 1) is payments[0]
        assert two_cents.get_payment(session, 2) is payments[1]

        payments[0].assign('groceries')

        assert groceries.balance == approx(-100)
        assert restaurants.balance == approx(0)

        with pytest.raises(two_cents.AssignmentError):
            payments[0].assign('groceries')
        with pytest.raises(two_cents.NoSuchBudget):
            payments[0].assign('nonexistant-budget')
        with pytest.raises(two_cents.AssignmentError):
            payments[0].ignore()

        payments[1].ignore()

        assert groceries.balance == approx(-100)
        assert restaurants.balance == approx(0)

        payments[1].assign('groceries')

        assert groceries.balance == approx(-110)
        assert restaurants.balance == approx(-00)

        payments[1].assign('restaurants')

        assert groceries.balance == approx(-100)
        assert restaurants.balance == approx(-10)
        assert two_cents.get_payments(session, 'groceries') == [payments[0]]
        assert two_cents.get_payments(session, 'restaurants') == [payments[1]]

        credit = add_payment(bank, 110)
        credit.assign('groceries')

        assert groceries.balance == approx(10)
        assert restaurants.balance == approx(-10)

def test_bank_schema(fresh_test_db):
    with open_test_db() as session:
        assert two_cents.get_num_banks(session) == 0
        assert two_cents.get_banks(session) == []
        assert not two_cents.bank_exists(session, 'wells_fargo')

        with pytest.raises(two_cents.NoSuchBank):
            assert two_cents.get_bank(session, 'wells_fargo')

        bank, payments, budgets = fill_database(session)

        assert two_cents.get_num_banks(session) == 1
        assert two_cents.get_banks(session) == [bank]
        assert two_cents.bank_exists(session, 'wells_fargo')
        assert bank.title == 'Wells Fargo'

        with pytest.raises(two_cents.UserError):
            add_bank(session)  # Can't add duplicate banks.
        with pytest.raises(two_cents.UserError):
            add_bank(session, 'nonexistant_scraper')

def test_suggest_allowance(fresh_test_db):
    with open_test_db() as session:
        bank, payments, budgets = fill_database(session)

        assert two_cents.suggest_allowance(session, budgets[0]) == 0
        assert two_cents.suggest_allowance(session, budgets[1]) == 0

        payments[0].assign(budgets[0].name)
        payments[1].assign(budgets[1].name)

        assert two_cents.suggest_allowance(session, budgets[0]) == 0
        assert two_cents.suggest_allowance(session, budgets[1]) == 0

        change_date('tomorrow')

        assert two_cents.suggest_allowance(session, budgets[0]) == approx(2966.666666666667)
        assert two_cents.suggest_allowance(session, budgets[1]) == approx(296.6666666666667)

def test_transfer_money(fresh_test_db):
    with open_test_db() as session:
        bank, payments, budgets = fill_database(session)

        two_cents.transfer_money(100, budgets[0], budgets[1])
        assert budgets[0].balance == -100
        assert budgets[1].balance == 100

        two_cents.transfer_money(50, budgets[1], budgets[0])
        assert budgets[0].balance == -50
        assert budgets[1].balance == 50

        two_cents.transfer_money(50, budgets[1], budgets[0])
        assert budgets[0].balance == 0
        assert budgets[1].balance == 0

def test_transfer_allowance(fresh_test_db):
    from two_cents import parse_allowance

    with open_test_db() as session:
        bank, payments, budgets = fill_database(session)

        budgets[0].allowance = parse_allowance('150 per month')
        budgets[1].allowance = parse_allowance('100 per month')

        two_cents.transfer_allowance('', budgets[0], budgets[1])

        assert budgets[0].allowance == approx(parse_allowance('150 per month'))
        assert budgets[1].allowance == approx(parse_allowance('100 per month'))

        two_cents.transfer_allowance('30 per month', budgets[0], budgets[1])

        assert budgets[0].allowance == approx(parse_allowance('120 per month'))
        assert budgets[1].allowance == approx(parse_allowance('130 per month'))

def test_parse_dollars(fresh_test_db):
    f = two_cents.parse_dollars

    assert f('$50.00') == approx(50)
    assert f('50.00') == approx(50)
    assert f('50') == approx(50)
    assert f(50) == approx(50)

    assert f('-$50.00') == approx(-50)
    assert f('-50.00') == approx(-50)
    assert f('-50') == approx(-50)
    assert f(-50) == approx(-50)

    with pytest.raises(two_cents.MoneyError):
        f('nan')
    with pytest.raises(two_cents.MoneyError):
        f('inf')
    with pytest.raises(two_cents.MoneyError):
        f('-inf')
    with pytest.raises(two_cents.MoneyError):
        f('spam')

def test_parse_allowance(fresh_test_db):
    f = two_cents.parse_allowance

    assert f('5 per day') == approx(5)
    assert f('$5 per day') == approx(5)
    assert f('$5/day') == approx(5)
    assert f('150 per month') == approx(150 * 12 / 356)
    assert f('150 per mo') == approx(150 * 12 / 356)
    assert f('100 per year') == approx(100 / 356)
    assert f('') == 0

    with pytest.raises(two_cents.AllowanceError):
        f('5 per')
    with pytest.raises(two_cents.AllowanceError):
        f('per day')
    with pytest.raises(two_cents.AllowanceError):
        f('5 day')
    with pytest.raises(two_cents.AllowanceError):
        f('five per day')
    with pytest.raises(two_cents.AllowanceError):
        f('five / day')
    with pytest.raises(two_cents.AllowanceError):
        f('5 per week')
    with pytest.raises(two_cents.AllowanceError):
        f('5 5 per day')
    with pytest.raises(two_cents.AllowanceError):
        f('5e0 per day')

def test_format_date(fresh_test_db):
    f = lambda x: two_cents.format_date(test_dates[x])
    assert f('today') == '01/01/14'
    assert f('tomorrow') == '01/02/14'
    assert f('next week') == '01/08/14'
    assert f('next month') == '02/01/14'
    assert f('next year') == '01/01/15'

def test_format_dollars(fresh_test_db):
    f = two_cents.format_dollars
    assert f(-100) == '-$100.00'
    assert f(-10) == '-$10.00'
    assert f(-1) == '-$1.00'
    assert f(0) == '$0.00'
    assert f(1) == '$1.00'
    assert f(10) == '$10.00'
    assert f(100) == '$100.00'

