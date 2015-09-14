#!/usr/bin/env python3

import pytest, datetime
import two_cents

test_db_path = './two_cents.db'
test_dates = {
        'today': datetime.datetime(2014, 1, 1),
        'tomorrow': datetime.datetime(2014, 1, 2),
        'next week': datetime.datetime(2014, 1, 8),
        'next month': datetime.datetime(2014, 2, 1),
        'next year': datetime.datetime(2015, 1, 1),
}


class approx:

    def __init__(self, expected, plus_or_minus=1e-5):
        self.expected = expected
        self.plus_or_minus = plus_or_minus

    def __repr__(self):
        return '{}±{}'.format(self.expected, self.plus_or_minus)

    def __eq__(self, actual):
        from collections import Iterable
        expected = self.expected
        eps = self.plus_or_minus

        if isinstance(actual, Iterable) and isinstance(expected, Iterable):
            return all(abs(a - x) < eps for a, x in zip(actual, expected))
        else:
            return abs(actual - expected) < eps


@pytest.fixture
def fresh_test_db():
    from os import remove
    try: remove(test_db_path)
    except FileNotFoundError: pass
    change_date('today')

def open_test_db():
    return two_cents.open_db(test_db_path)

def change_date(date):
    # Monkey-patch the function that two_cents uses to figure out the current 
    # date and time.
    two_cents.model.now = lambda: test_dates[date]

def fill_database(session):
    bank = add_bank(session)
    payments = [
            add_payment(bank, -100),
            add_payment(bank, -10),
    ]
    budgets = [
            add_budget(session, 'groceries', '0', ''),
            add_budget(session, 'restaurants', '0', ''),
    ]
    return bank, payments, budgets

def add_bank(session, scraper_key='wells_fargo'):
    bank = two_cents.Bank(session, scraper_key)
    session.add(bank)
    return bank

def add_payment(bank, value=-100, date='today'):
    payment = two_cents.Payment('???', '???', test_dates[date].date(), value, '???')
    bank.payments.append(payment)
    return payment

def add_budget(session, name, balance=0, allowance=''):
    budget = two_cents.Budget(name, balance, allowance)
    session.add(budget)
    return budget


