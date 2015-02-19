#!/usr/bin/env python3

## Imports
from __future__ import division

import datetime
import os
import shlex
import sqlalchemy
import subprocess
import re
import textwrap

from pprint import pprint
from contextlib import contextmanager
from sqlalchemy.orm import *
from sqlalchemy.schema import *
from sqlalchemy.types import *
from sqlalchemy.ext.declarative import declarative_base

import banking

## Schema Types
Session = sessionmaker()
Base = declarative_base()
Cents = Integer
Days = Integer


class Budget (Base):
    __tablename__ = 'budgets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    balance = Column(Cents, nullable=False)
    allowance = Column(String)
    last_update = Column(Date, nullable=False)

    def __init__(self, name, balance=None, allowance=None):
        self.name = name
        self.balance = balance or 0
        self.allowance = allowance or ''
        self.last_update = today()

    def __repr__(self):
        repr = '<budget name={0.name} balance={0.balance} ' + \
                ('allowance={0.allowance}>' if self.allowance else '>')
        return repr.format(self)

    @property
    def balance_in_dollars(self):
        return format_value(self.balance)

    def update_allowance(self):
        this_update = today()
        last_update = self.last_update

        cents_per_day = parse_allowance(self.allowance)
        days_elapsed = (this_update - last_update).days

        self.balance += cents_per_day * days_elapsed
        self.last_update = this_update

        session = Session.object_session(self)
        session.commit()

    def show(self, indent=''):
        print('{}{} {}'.format(indent, self.name, format_value(self.balance)))


def get_budget(session, name):
    try:
        return session.query(Budget).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchBudget(name)

def get_budgets(session):
    return session.query(Budget).all()

def get_num_budgets(session):
    return session.query(Budget).count()

def budget_exists(session, name):
    return session.query(Budget).filter_by(name=name).count() > 0


class Payment (Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey('banks.id'))
    account_id = Column(String)
    transaction_id = Column(String)
    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)
    description = Column(Text)
    assignment = Column(String)
    ignored = Column(Boolean, nullable=False)

    def __init__(self, acct_id, txn_id, date, value, description):
        self.account_id = acct_id
        self.transaction_id = txn_id
        self.date = date
        self.value = value
        self.description = description
        self.ignored = False

    def __repr__(self):
        return '<Payment acct_id={} txn_id={}>'.format(self.account_id, self.transaction_id)
        date = format_date(self.date)
        value = format_value(self.value)
        assignment = self.assignment or 'unassigned'
        return '<Payment id={} date={} value={} assignment={}>'.format(
                self.id, date, value, assignment)

    def __eq__(self, other):
        self_id = self.account_id, self.transaction_id
        other_id = other.account_id, other.transaction_id
        return self_id == other_id

    def assign(self, assignment):
        """
        Specify which budgets should cover this payment.  A payment can be 
        split and assigned to multiple budgets.  If the payment was already 
        assigned before this call, the old budgets will be credited the value 
        they were originally assigned and the new budgets will be debited as 
        appropriate.
        """

        session = Session.object_session(self)

        # Unassign the payment from any budgets it was previously assigned to.

        if self.assignment is not None:
            for name, value in parse_assignment(
                    self.assignment, self.value).items():
                try:
                    budget = get_budget(session, name)
                    budget.balance -= value
                except NoSuchBudget:
                    pass

        # Assign the payment to the specified budgets.

        for name, value in parse_assignment(
                assignment, self.assignable_value).items():
            try:
                budget = get_budget(session, name)
                budget.balance += value
            except NoSuchBudget:
                raise AssignmentError(assignment, "no such budget '{}'".format(name))

        # Note that self.assignable_value will return 0 once self.assignment is 
        # set.  That's why this line comes after the logic above.

        self.assignment = assignment
        self.ignored = False

        session.commit()

    def ignore(self):
        assert self.assignment is None
        self.ignored = True

        session = Session.object_session(self)
        session.commit()

    def show(self, indent=''):
        print("{}Date:    {}".format(indent, format_date(self.date)))
        print("{}Value:   {}".format(indent, format_value(self.value)))
        print("{}Bank:    {}".format(indent, self.bank.title))

        if len(self.description) < (79 - len(indent) - 13):
            print("{}Description: {}".format(indent, self.description))
        else:
            description = textwrap.wrap(
                    self.description,
                    initial_indent=indent+'  ', subsequent_indent=indent+'  ')

            print("{}Description:".format(indent))
            print('\n'.join(description))

    @property
    def assignable_value(self):
        """
        Return the total value of this payment that is either unassigned or 
        assigned to budgets that still exist.  Value assigned to budgets that 
        no longer exist cannot be reassigned.
        """
        assignable_value = self.value
        session = Session.object_session(self)

        if self.assignment is not None:
            for budget_name, value in parse_assignment(
                    self.assignment, self.value).items():
                if not budget_exists(session, budget_name):
                    assignable_value -= value

        return assignable_value


def get_unassigned_payments(session):
    return session.query(Payment).filter_by(assignment=None, ignored=False).all()

def get_num_unassigned_payments(session):
    return session.query(Payment).filter_by(assignment=None, ignored=False).count()


class Bank (Base):
    __tablename__ = 'banks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scraper_key = Column(String, unique=True, nullable=False)
    username_command = Column(String)
    password_command = Column(String)
    payments = relationship("Payment", backref="bank")
    last_update = Column(Date)

    def __init__(self, scraper_key, username_command, password_command):
        self.scraper_key = scraper_key
        self.username_command = username_command
        self.password_command = password_command
        self.last_update = today()

    def download_payments(self, username_callback, password_callback):
        """
        Download new transactions from this bank.
        """

        # Get a username and password the scraper can use to download data from 
        # this bank.  Commands to generate user names and passwords can be 
        # stored in the database, so use those if they're present.  Otherwise 
        # prompt the user for the needed information.

        def get_user_info(command, interactive_prompt):
            error_message = ""

            if command:
                try:
                    with open(os.devnull, 'w') as devnull:
                        user_info = subprocess.check_output(
                                shlex.split(command), stderr=devnull)
                        return user_info.decode('ascii').strip('\n')
                except subprocess.CalledProcessError as error:
                    error_message = "Command '{}' returned non-zero exit status {}".format(command, error.returncode)

            return interactive_prompt(self.title, error_message)

        username = get_user_info(self.username_command, username_callback)
        password = get_user_info(self.password_command, password_callback)

        # Scrape new transactions from the bank website, and store those 
        # transactions in the database as payments.

        session = Session.object_session(self)
        scraper_class = scraper_classes[self.scraper_key]
        scraper = scraper_class(username, password)
        start_date = self.last_update - datetime.timedelta(days=30)

        for account in scraper.download(start_date):
            for transaction in account.statement.transactions:
                payment = Payment(
                        account.number,
                        transaction.id,
                        transaction.date,
                        to_cents(transaction.amount),
                        transaction.payee + ' ' + transaction.memo)

                if payment not in self.payments:
                    self.payments.append(payment)

        self.last_update = today()
        session.commit()

    @property
    def title(self):
        return scraper_titles[self.scraper_key]


def get_bank(session, name):
    try:
        return session.query(Bank).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchBank(name)

def get_banks(session):
    return session.query(Bank).all()

def get_num_banks(session):
    return session.query(Bank).count()

def bank_exists(session, key):
    return session.query(Bank).filter_by(scraper_key=key).count() > 0


scraper_classes = {
        'wells_fargo': banking.WellsFargo,
}

scraper_titles = {
        'wells_fargo': 'Wells Fargo',
}


@contextmanager
def open_db(path=None):
    try:
        # Create a new session.
        path = path or '~/.config/budget/budget.db'
        url = 'sqlite:///' + os.path.expanduser(path)
        engine = sqlalchemy.create_engine(url)
        session = sqlalchemy.orm.sessionmaker(bind=engine)()

        # Make sure the database is properly set up.
        Base.metadata.create_all(engine)

        # Return the session.
        yield session
        session.commit()

    except (KeyboardInterrupt, EOFError):
        session.rollback()
        print()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def download_payments(session, username_callback, password_callback):
    for bank in get_banks(session):
        bank.download_payments(username_callback, password_callback)

def update_allowances(session):
    for budget in get_budgets(session):
        budget.update_allowance()

def parse_assignment(assignment, value):
    """
    Use the given assignment string to determine how the given value (in cents) 
    should be assigned to one or more budgets.
    
    Each assignment must be expressed as an budget name followed optionally by 
    an equal sign and a dollar value.  The full assignment string can contain 
    multiple assignments can be separated with spaces, although this means that 
    each assignment cannot contain any spaces (e.g. around the equal sign).  
    Budgets with dollar values are referred to as explicit budgets, while 
    those without are referred to as implicit.  The total value the explicit 
    budgets may not exceed the value of the receipt.  Any value leftover after 
    the explicit budgets are considered is divided evenly between the implicit 
    budgets.  The most common case is that only one implicit budget will be 
    given.  In this case, the entire value is charged to the that budget.

    >>> parse_assignment('A', 100) == {'A': 100}
    True

    >>> parse_assignment('A B', 100) == {'A': 50, 'B': 50}
    True

    >>> parse_assignment('A=0.7 B', 100) == {'A': 70, 'B': 30}
    True

    >>> parse_assignment('A B=0.7', 100) == {'A': 30, 'B': 70}
    True

    >>> parse_assignment('A=0.7 B C', 100) == {'A': 70, 'B': 15, 'C': 15}
    True

    >>> parse_assignment('A=0.7 B=0.2 C', 100) == {'A': 70, 'B': 20, 'C': 10}
    True
    """

    import re
    import math

    split_pattern = re.compile(r'(\w*)=([\d.]*)')
    raw_value = value
    total_value = abs(value)
    total_value_string = format_value(total_value)

    # Parse the given assignment.

    implicit_budgets = []
    explicit_budgets = {}

    if not assignment:
        raise AssignmentError(assignment, "no assignment given")

    for token in assignment.split():
        match = split_pattern.match(token)
        if match:
            token_name, token_value = match.groups()
            token_value = to_cents(token_value)
            explicit_budgets[token_name] = abs(token_value)
        else:
            implicit_budgets.append(token)

    processed_budgets = explicit_budgets
    explicit_value = sum(explicit_budgets.values())

    # Complain if too much money has been allocated.

    if explicit_value > total_value:
        raise AssignmentError(assignment,
                'more than {} assigned'.format(total_value_string))

    # Determine how much money should be assigned to the implicit budgets.

    if implicit_budgets:
        implicit_value = total_value - explicit_value
        value_chunk = implicit_value // len(implicit_budgets)

        if value_chunk == 0:
            raise AssignmentError(assignment,
                    "no money assigned to implicit budgets")

        for name in implicit_budgets:
            processed_budgets[name] = value_chunk
            implicit_value -= value_chunk

        remainder_budget = implicit_budgets[-1]
        processed_budgets[remainder_budget] += implicit_value

    # Complain if too little money has been allocated.  This can only 
    # happen if no implicit budget were given.

    if sum(processed_budgets.values()) < total_value:
        assert not implicit_budgets
        raise AssignmentError(assignment,
                "less than {} assigned".format(total_value_string))

    # Reapply the correct signs to the results.  Before this point, every 
    # value was made positive to simplify the algorithm.

    fix_sign = lambda x: int(math.copysign(x, raw_value))

    for budget, value in processed_budgets.items():
        processed_budgets[budget] = fix_sign(value)

    # Return a dictionary which tells how much of the original value is 
    # assigned to each budget.

    return processed_budgets

def parse_allowance(allowance):
    """
    Convert the given allowance to cents per day.

    An allowance is a string that represents some amount of money per time.  
    Each allowance is expected to have three words.  The first is a dollar 
    amount (which may or may not be preceded by a dollar sign), the second is 
    the literal "per", and the third is either "day", "month", or "year".  The 
    return value is an integer value in units of cents per day.

    >>> parse_allowance('5 per day')
    500

    >>> parse_allowance('$5 per day')
    500

    >>> parse_allowance('150 per month')
    505

    >>> parse_allowance('100 per year')
    28

    >>> parse_allowance('')
    0
    """

    if allowance == '':
        return 0

    allowance_pattern = re.compile('(\$?[0-9.]+) per (\w+)')
    allowance_match = allowance_pattern.match(allowance)

    if not allowance_match:
        raise AllowanceError(allowance, "doesn't match '<money> per <day|month|year>'")

    money_token, time_token = allowance_match.groups()

    cents = to_cents(money_token)

    if time_token == 'day':
        days = 1
    elif time_token == 'month':
        days = 356 / 12
    elif time_token == 'year':
        days = 356
    else:
        raise AllowanceError(allowance, "must be 'per day', 'per month', or 'per year'")

    return int(cents // days)

def format_date(date):
    return date.strftime('%m/%d/%y')

def format_value(value):
    if value < 0:
        value = abs(value)
        return '-${}.{:02d}'.format(value // 100, value % 100)
    else:
        return '${}.{:02d}'.format(value // 100, value % 100)

def to_cents(dollars):
    """
    Convert the dollar input value to cents.

    The input may either be a numeric value or a string.  If it's a string, a 
    leading dollar sign may or may not be present.
    """
    try: dollars = dollars.replace('$', '')
    except AttributeError: pass
    return int(100 * float(dollars))

def today():
    """
    Return today's date.  This function is important because it can be 
    monkey-patched during testing make the whole program deterministic.  It's 
    also a bit more convenient than the function in datetime.
    """
    return datetime.date.today()


class BudgetError (Exception):

    def __init__(self, message=''):
        self.message = message

    def __str__(self):
        return self.message


class AllowanceError (BudgetError):

    def __init__(self, allowance, message):
        if allowance is not None:
            self.message = "'{}': {}".format(allowance, message)
        else:
            self.message = message

        
class AssignmentError (BudgetError):

    def __init__(self, assignment, message):
        if assignment is not None:
            self.message = "'{}': {}".format(assignment, message)
        else:
            self.message = message

        self.raw_message = message


class NoSuchBudget (BudgetError):
    pass

class NoSuchBank (BudgetError):
    pass


if __name__ == '__main__':
    import doctest
    doctest.testmod()
