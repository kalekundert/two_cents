#!/usr/bin/env python3

## Imports
import datetime
import os
import shlex
import sqlalchemy
import subprocess
import re

from contextlib import contextmanager
from sqlalchemy.orm import *
from sqlalchemy.schema import *
from sqlalchemy.types import *
from sqlalchemy.ext.declarative import declarative_base

from . import banks

## Schema Types
Session = sessionmaker()
Base = declarative_base()
Dollars = Float
DollarsPerDay = Float


seconds_per_day = 86400
days_per_month = 356 / 12
days_per_year = 356

class Budget (Base):
    __tablename__ = 'budgets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    balance = Column(Dollars, nullable=False)
    allowance = Column(DollarsPerDay, nullable=False)
    last_update = Column(DateTime, nullable=False)

    def __init__(self, name, balance=None, allowance=None):
        self.name = name
        self.balance = int(balance or 0)
        self.allowance = parse_allowance(allowance or '')
        self.last_update = now()

        if name in ('skip', 'ignore'):
            raise UserError("can't name a budget 'skip' or 'ignore'")

    def __repr__(self):  # pragma: no cover
        repr = '<budget name={0.name} balance={0.balance}' + \
                (' allowance={0.allowance}>' if self.allowance else '>')
        return repr.format(self)

    @property
    def pretty_balance(self):
        return format_dollars(self.balance)

    @property
    def pretty_allowance(self):
        return format_dollars(self.allowance * days_per_month) + '/mo'

    @property
    def recovery_time(self):
        """
        Return the number of days it will take this account to reach a positive 
        balance, assuming no more payments are made.  If the account is already 
        positive, return 0.  If the account will never become positive (i.e. it 
        has no allowance), return -1.
        """
        from math import ceil

        if self.balance >= 0:
            return 0

        if self.allowance <= 0:
            return -1

        return int(ceil(abs(self.balance / self.allowance)))

    def update_allowance(self):
        this_update = now()
        last_update = self.last_update

        dollars_per_second = self.allowance / seconds_per_day
        seconds_elapsed = (this_update - last_update).total_seconds()

        self.balance += dollars_per_second * seconds_elapsed
        self.last_update = this_update


def get_budget(session, name):
    try:
        return session.query(Budget).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchBudget(name)

def get_budgets(session, *names):
    budgets = session.query(Budget).all()
    if names: budgets = [x for x in budgets if x.name in names]
    return budgets

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

    def __repr__(self):  # pragma: no cover
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
        Specify which budget should cover this payment.  If the payment was 
        already assigned before this call, the old budget will be credited and 
        the new budgets will be debited as appropriate.
        """

        session = Session.object_session(self)

        # Warn the user if the new assignment is the same as the old one.
        
        if assignment == self.assignment:
            raise AssignmentError("Payment #{} is already assigned to '{}'".format(self.id, assignment))

        # Make sure the new assignment actually exists.

        try:
            new_budget = get_budget(session, assignment)
        except NoSuchBudget:
            raise NoSuchBudget(assignment)

        # If this payment was already assigned to another budget, make sure 
        # that budget still exists.  If it doesn't, raise an exception because 
        # there's no way to credit the value of this payment.  If it does, then 
        # credit it the value of this payment.

        if self.assignment not in (None, 'ignore'):
            try:
                old_budget = get_budget(session, self.assignment)
            except NoSuchBudget:
                raise AssignmentError("Payment #{} assigned to '{}', which no longer exists.".format(self.id, self.assignment))

            old_budget.balance -= self.value

        # Debit the new assignment the value of this payment.

        new_budget.balance += self.value
        self.assignment = assignment

    def ignore(self):
        if self.assignment is None:
            self.assignment = 'ignore'
        else:
            raise AssignmentError("Payment can't be ignored because it's already assigned to '{}'.".format(self.assignment))


def get_payment(session, id):
    payment = session.query(Payment).get(id)
    if payment is None: raise NoSuchPayment(id)
    else: return payment

def get_payments(session, budget_name=None):
    if budget_name is not None:
        return session.query(Payment).filter_by(assignment=budget_name).all()
    else:
        return session.query(Payment).all()

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

    def __init__(self, session, scraper_key):
        if bank_exists(session, scraper_key):
            raise UserError("Bank '{}' already exists.".format(scraper_key))
        if scraper_key not in scraper_classes:
            raise NoSuchScraper(scraper_key)

        self.scraper_key = scraper_key
        self.username_command = None
        self.password_command = None
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

    @property
    def title(self):
        return scraper_titles[self.scraper_key]


def get_bank(session, key):
    try:
        return session.query(Bank).filter_by(scraper_key=key).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchBank(key)

def get_banks(session):
    return session.query(Bank).all()

def get_num_banks(session):
    return session.query(Bank).count()

def bank_exists(session, key):
    return session.query(Bank).filter_by(scraper_key=key).count() > 0


scraper_classes = {
        'wells_fargo': banks.WellsFargo,
}

scraper_titles = {
        'wells_fargo': 'Wells Fargo',
}


@contextmanager
def open_db(path):
    # Make sure the database directory exists.

    path = os.path.abspath(os.path.expanduser(path))
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

def suggest_allowance(session, budget):
    """
    Suggest a reasonable allowance for the given account its rate of spending 
    to date.  More specifically, this function calculates the average amount of 
    spending for the given account and returns that information in units of 
    dollars per month.
    """
    payments = get_payments(session, budget.name)

    if not payments:
        return 0

    elapsed_money = sum(x.value for x in payments)
    elapsed_time = now().date() - min(x.date for x in payments)

    if not elapsed_time.days:
        return 0

    return -elapsed_money / elapsed_time.days * days_per_month

def transfer_money(dollars, from_budget, to_budget):
    from_budget.balance -= dollars
    to_budget.balance += dollars

def transfer_allowance(allowance, from_budget, to_budget):
    dollars_per_day = parse_allowance(allowance)
    from_budget.allowance -= dollars_per_day
    to_budget.allowance += dollars_per_day

def parse_dollars(value):
    """
    Convert the input dollar value to a numeric value.

    The input may either be a numeric value or a string.  If it's a string, a 
    leading dollar sign may or may not be present.
    """
    try: value = value.replace('$', '')
    except AttributeError: pass

    try: dollars = float(value)
    except: raise MoneyError(value)

    from math import isfinite
    if not isfinite(dollars): raise MoneyError(value)

    return dollars

def parse_allowance(allowance):
    """
    Convert the given allowance to dollars per day.

    An allowance is a string that represents some amount of money per time.  
    Each allowance is expected to have three tokens.  The first is a dollar 
    amount (which may be preceded by a dollar sign), the second is either "/" 
    or " per ", and the third is one of "day", "month", "mo", or "year".  If 
    the given allowance is properly formatted, this function returns a float in 
    units of dollars per day.  Otherwise an AllowanceError is raised.
    """

    if allowance == '':
        return 0

    allowance_pattern = re.compile('(\$?[0-9.]+)(/| per )(day|month|mo|year)')
    allowance_match = allowance_pattern.match(allowance)

    if not allowance_match:
        raise AllowanceError(allowance, "doesn't match '<money> per <day|month|year>'")

    money_token, sep, time_token = allowance_match.groups()

    dollars = parse_dollars(money_token)

    if time_token == 'day':
        days = 1
    elif time_token in ('month', 'mo'):
        days = days_per_month
    elif time_token == 'year':
        days = days_per_year
    else:
        raise AssertionError    # pragma: no cover

    return dollars / days

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


class UserError (Exception):

    def __init__(self, message=''):
        self.message = message

    def __str__(self):
        return self.message


class AllowanceError (UserError):

    def __init__(self, allowance, message):
        if allowance is not None:
            self.message = "'{}': {}".format(allowance, message)
        else:
            self.message = message

        
class AssignmentError (UserError):
    pass

class MoneyError (UserError):

    def __init__(self, value):
        self.message = "Expected a dollar value, not '{}'.".format(value)


class NoSuchBudget (UserError):

    def __init__(self, name):
        self.message = "No budget named '{}'.".format(name)


class NoSuchPayment (UserError):

    def __init__(self, payment_id):
        self.message = "No payment with id='{}'.".format(payment_id)


class NoSuchBank (UserError):

    def __init__(self, scraper_key):
        self.message = "No bank named '{}'.".format(scraper_key)


class NoSuchScraper (UserError):

    def __init__(self, scraper_key):
        self.message = "Bank '{}' is not supported.\n".format(scraper_key)
        if len(scraper_classes) == 1:
            self.message += "Only '{}' is supported at present.".format(list(scraper_classes.keys())[0])
        else:
            self.message += "Supported banks: " + ', '.join("'{}'".format(x) for x in scraper_classes)



