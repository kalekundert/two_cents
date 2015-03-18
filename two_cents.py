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
Dollars = Float


db_path = '~/.config/twocents/budgets.db'
seconds_per_day = 86400
seconds_per_month = 86400 * 356 / 12
seconds_per_year = 86400 * 356

class Budget (Base):
    __tablename__ = 'budgets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    balance = Column(Dollars, nullable=False)
    allowance = Column(String)
    last_update = Column(DateTime, nullable=False)

    def __init__(self, name, balance=None, allowance=None):
        self.name = name
        self.balance = balance or 0
        self.allowance = allowance or ''
        self.last_update = now()

        if name in ('skip', 'ignore'):
            raise BudgetError("can't name a budget 'skip' or 'ignore'")

    def __repr__(self):
        repr = '<budget name={0.name} balance={0.balance} ' + \
                ('allowance={0.allowance}>' if self.allowance else '>')
        return repr.format(self)

    @property
    def pretty_balance(self):
        return format_dollars(self.balance)

    @property
    def recovery_time(self):
        """
        Return the number of days it will take this account to reach a positive 
        balance, assuming no more payments are made.  If the account is already 
        positive, return 0.  If the account will never become positive (i.e. it 
        has no allowance), return -1.
        """
        from math import ceil

        if self.balance > 0:
            return 0

        dollars_per_second = parse_allowance(self.allowance)
        dollars_per_day = dollars_per_second * seconds_per_day

        if dollars_per_day <= 0:
            return -1

        return int(ceil(abs(self.balance / dollars_per_day)))

    def update_allowance(self):
        this_update = now()
        last_update = self.last_update

        dollars_per_second = parse_allowance(self.allowance)
        seconds_elapsed = (this_update - last_update).total_seconds()

        self.balance += dollars_per_second * seconds_elapsed
        self.last_update = this_update

        session = Session.object_session(self)
        session.commit()

    def show(self, indent=''):
        print('{}{} {}'.format(indent, self.name, format_dollars(self.balance)))


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
    value = Column(Dollars, nullable=False)
    description = Column(Text)
    assignment = Column(String)

    def __init__(self, acct_id, txn_id, date, value, description):
        self.account_id = acct_id
        self.transaction_id = txn_id
        self.date = date
        self.value = parse_dollars(value)
        self.description = description

    def __repr__(self):
        return '<Payment acct_id={} txn_id={}>'.format(self.account_id, self.transaction_id)
        date = format_date(self.date)
        value = format_dollars(self.value)
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
        session.commit()

    def ignore(self):
        assert self.assignment is None
        self.assignment = 'ignore'

        session = Session.object_session(self)
        session.commit()

    def show(self, indent=''):
        print("{}Date:    {}".format(indent, format_date(self.date)))
        print("{}Value:   {}".format(indent, format_dollars(self.value)))
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
        Return the total value of this payment that is either unassigned, 
        ignored, or assigned to budgets that still exist.  Value assigned to 
        budgets that no longer exist cannot be reassigned.
        """
        assignable_value = self.value
        session = Session.object_session(self)

        if self.assignment is not None:
            for budget_name, value in parse_assignment(
                    self.assignment, self.value).items():
                if budget_name == 'ignore':
                    continue
                if not budget_exists(session, budget_name):
                    assignable_value -= value

        return assignable_value


def get_unassigned_payments(session):
    return session.query(Payment).filter_by(assignment=None).all()

def get_num_unassigned_payments(session):
    return session.query(Payment).filter_by(assignment=None).count()


class Bank (Base):
    __tablename__ = 'banks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scraper_key = Column(String, unique=True, nullable=False)
    username_command = Column(String)
    password_command = Column(String)
    payments = relationship("Payment", backref="bank")
    last_update = Column(DateTime)

    def __init__(self, scraper_key, username_command, password_command):
        self.scraper_key = scraper_key
        self.username_command = username_command
        self.password_command = password_command
        self.last_update = now()

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
                        transaction.amount,
                        transaction.payee + ' ' + transaction.memo)

                if payment not in self.payments:
                    self.payments.append(payment)

        self.last_update = now()
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
def open_db(path=db_path):
    # Make sure the database directory exists.

    path = os.path.expanduser(path)
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))

    # Create an database session.  Currently the whole program is hard-coded to 
    # use SQLite, but in the future I may want to use MySQL to make budgets 
    # accessible from many devices.

    engine = sqlalchemy.create_engine('sqlite:///' + path)
    Base.metadata.create_all(engine)
    session = sqlalchemy.orm.sessionmaker(bind=engine)()

    # Return the session to the calling code.  If the calling code completes 
    # without error, commit and close the session.  Otherwise, rollback the 
    # session to prevent bad data from being written to the database.

    try:
        yield session
        session.commit()
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

def parse_dollars(value):
    """
    Convert the input dollar value to a numeric value.

    The input may either be a numeric value or a string.  If it's a string, a 
    leading dollar sign may or may not be present.
    """
    try: value = value.replace('$', '')
    except AttributeError: pass
    return float(value)

def parse_assignment(assignment, value):
    """
    Use the given assignment string to determine how the given dollar value 
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

    >>> parse_assignment('A=70 B', 100) == {'A': 70, 'B': 30}
    True

    >>> parse_assignment('A B=70', 100) == {'A': 30, 'B': 70}
    True

    >>> parse_assignment('A=70 B C', 100) == {'A': 70, 'B': 15, 'C': 15}
    True

    >>> parse_assignment('A=70 B=20 C', 100) == {'A': 70, 'B': 20, 'C': 10}
    True
    """

    import re
    import math

    split_pattern = re.compile(r'(\w*)=([\d.]*)')
    raw_value = value
    total_value = abs(value)
    total_value_string = format_dollars(total_value)

    # Parse the given assignment.

    implicit_budgets = []
    explicit_budgets = {}

    if not assignment:
        raise AssignmentError(assignment, "no assignment given")

    for token in assignment.split():
        match = split_pattern.match(token)
        if match:
            token_name, token_value = match.groups()
            token_value = parse_dollars(token_value)
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
    Convert the given allowance to dollars per second.

    An allowance is a string that represents some amount of money per time.  
    Each allowance is expected to have three words.  The first is a dollar 
    amount (which may be preceded by a dollar sign), the second is the literal 
    string "per", and the third is one of "day", "month", or "year".  If the 
    given allowance is properly formatted, this function returns a float in 
    units of dollars per second.  Otherwise an AllowanceError is raised.

    >>> parse_allowance('5 per day')
    5.787037037037037e-05

    >>> parse_allowance('$5 per day')
    5.787037037037037e-05

    >>> parse_allowance('150 per month')
    5.7077625570776254e-05

    >>> parse_allowance('100 per year')
    3.1709791983764586e-06

    >>> parse_allowance('')
    0
    """

    if allowance == '':
        return 0

    allowance_pattern = re.compile('(\$?[0-9.]+) per (day|month|year)')
    allowance_match = allowance_pattern.match(allowance)

    if not allowance_match:
        raise AllowanceError(allowance, "doesn't match '<money> per <day|month|year>'")

    money_token, time_token = allowance_match.groups()

    dollars = parse_dollars(money_token)

    if time_token == 'day':
        seconds = seconds_per_day
    elif time_token == 'month':
        seconds = seconds_per_month
    elif time_token == 'year':
        seconds = seconds_per_year
    else:
        raise AssertionError

    return dollars / seconds

def format_date(date):
    return date.strftime('%m/%d/%y')

def format_dollars(value):
    if value < 0:
        value = abs(value)
        return '-${:.2f}'.format(value)
    else:
        return '${:.2f}'.format(value)

def now():
    """
    Return today's date.  This function is important because it can be 
    monkey-patched during testing make the whole program deterministic.  It's 
    also a bit more convenient than the function in datetime.
    """
    return datetime.datetime.now()


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
