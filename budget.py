#!/usr/bin/env python3

# Imports (fold)
import datetime
import os
import subprocess
import shlex
import textwrap

import banking
import sqlalchemy
import yaml

from pprint import pprint
from contextlib import contextmanager
from sqlalchemy.orm import *
from sqlalchemy.schema import *
from sqlalchemy.types import *
from sqlalchemy.ext.declarative import declarative_base

# Schema Types (fold)
Base = declarative_base()
Cents = Integer
Days = Integer

class Money:
    pass

class Frequency:

    class Type (TypeDecorator):
        impl = String

        def process_bind_param(self, param, dialect):
            if isinstance(param, Frequency):
                return param.frequency
            else:
                Frequency.validate(param)
                return param

        def process_result_value(self, value, dialect):
            return Frequency(value)

        def copy(self):
            return Frequency.Type()


    def __init__(self, frequency):
        self.validate(frequency)
        self.frequency = frequency

    @staticmethod
    def validate(frequency):
        if frequency not in ('daily', 'monthly', 'yearly'):
            raise UnknownFrequency(frequency)
        
    def payments_due(self, last_update, date_canceled):
        this_update = today() if date_canceled is None else date_canceled
        days_elapsed = (this_update - last_update).days
        years_elapsed = this_update.year - last_update.year
        months_elapsed = \
                12 * years_elapsed + this_update.month - last_update.month

        if self.frequency == 'daily':
            return days_elapsed

        if self.frequency == 'monthly':
            return months_elapsed

        if self.frequency == 'yearly':
            return years_elapsed



class Account (Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    value = Column(Cents, nullable=False)

    payments = relationship('Payment', backref='account')
    allowances = relationship('Allowance', backref='account')

    transfers_in = relationship('Transfer', backref='payee',
            primaryjoin='Account.id == Transfer.payee_id')
    transfers_out = relationship('Transfer', backref='payer',
            primaryjoin='Account.id == Transfer.payer_id')

    def __init__(self, name, value=0):
        self.name = name
        self.value = value

    def __repr__(self):
        return '<account name={}>'.format(self.name)

    def show(self, indent=''):
        print('{0}{1} {2}'.format(indent, self.name, format_value(self.value)))

    def update(self, session):
        for allowance in self.allowances:
            allowance.update(session)


class Payment (Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)

    def __init__(self, account, date, value):
        self.account = account; account.value += value
        self.date = date
        self.value = value

    def __repr__(self):
        date = format_date(self.date)
        value = format_value(self.value)
        return '<debit id={} date={} value={}>'.format(self.id, date, value)


class Allowance (Base):
    __tablename__ = 'allowances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))

    update_value = Column(Cents, nullable=False)
    update_frequency = Column(Frequency.Type, nullable=False)
    last_updated = Column(Date, nullable=False)
    date_canceled = Column(Date)

    def __init__(self, account, value, frequency):
        self.account = account
        self.update_value = value
        self.update_frequency = frequency
        self.last_updated = today()
        self.date_canceled = None

    def __repr__(self):
        return '<budget id={} account={} value={} {}>'.format(
                self.id, self.account.id,
                self.update_value, self.update_frequency)

    def update(self, session):
        if self.date_canceled is not None:
            return

        self.account.value += self.update_value * \
                self.update_frequency.payments_due(
                        self.last_updated, self.date_canceled)

        self.last_updated = today()

        session.add(self)
        session.add(self.account)

    def cancel(self, session):
        self.update()
        self.date_canceled = today()
        assert self.last_update == self.date_canceled


class Transfer (Base):
    __tablename__ = 'transfers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    payer_id = Column(Integer, ForeignKey('accounts.id'))
    payee_id = Column(Integer, ForeignKey('accounts.id'))
    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)

    def __init__(self, payer, payee, date, value):
        self.payer = payer; payer.value -= value
        self.payee = payee; payee.value += value
        self.date = date
        self.value = value


class Savings (Base):
    __tablename__ = 'savings'

    id = Column(Integer, primary_key=True, autoincrement=True)

    update_value = Column(Cents, nullable=False)
    update_frequency = Column(Frequency.Type, nullable=False)
    last_updated = Column(Date, nullable=False)

    def __init__(self, value, frequency):
        self.update_value = value
        self.update_frequency = frequency

    def __repr__(self):
        return '<savings id={} value={} {}>'.format(
                self.id, self.update_value, self.update_frequency)

    def update(self):
        pass


class SavingsPayment (Payment):
    __tablename__ = 'savings_payments'

    id = Column(Integer, ForeignKey('payments.id'), primary_key=True)
    savings_id = Column(Integer, ForeignKey('savings.id'))

class Bank (Base):
    __tablename__ = 'banks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    username_command = Column(String)
    password_command = Column(String)
    last_update = Column(Date)

    receipts = relationship('BankReceipt', backref='bank')

    modules = {
            'wells-fargo': banking.WellsFargo
    }

    def __init__(self, name, username_command, password_command):
        self.name = name
        self.username_command = username_command
        self.password_command = password_command
        self.last_update = today()

    def update(self, session, username, password):
        scraper_class = self.modules[self.name]
        scraper = scraper_class(username, password)
        start_date = self.last_update - datetime.timedelta(days=30)

        for account in scraper.download(start_date):
            for transaction in account.statement.transactions:
                receipt = BankReceipt(
                        account.number,
                        transaction.id,
                        transaction.date,
                        to_cents(transaction.amount),
                        transaction.payee + ' ' + transaction.memo)

                if receipt not in self.receipts:
                    self.receipts.append(receipt)

        session.add(self)

    @property
    def title(self):
        return self.modules[self.name].title

    @property
    def username(self):
        if self.username_command:
            command = shlex.split(self.username_command)
            return subprocess.check_output(command).decode('ascii').strip('\n')
        else:
            raise AskForUsername(bank)

    @property
    def password(self):
        if self.password_command:
            command = shlex.split(self.password_command)
            return subprocess.check_output(command).decode('ascii').strip('\n')
        else:
            raise AskForPassword(bank)


class BankPayment (Payment):
    __tablename__ = 'bank_payments'

    id = Column(Integer, ForeignKey('payments.id'), primary_key=True)
    receipt_id = Column(Integer, ForeignKey('bank_receipts.id'))

    def __init__(self, account, receipt, value=None):
        if value is None: value = receipt.value
        Payment.__init__(self, account, receipt.date, value)
        self.receipt = receipt


class BankReceipt (Base):
    __tablename__ = 'bank_receipts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey('banks.id'))
    account_id = Column(String)
    transaction_id = Column(String)
    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)
    description = Column(Text)
    status = Column(Enum('unassigned', 'assigned', 'ignored'))

    payments = relationship('BankPayment', backref='receipt')

    def __init__(self, account_id, transaction_id, date, value, description):
        self.transaction_id = transaction_id
        self.account_id = account_id
        self.date = date
        self.value = value
        self.description = description
        self.status = 'unassigned'

    def __repr__(self):
        return '<bank_receipt acct={} txn={} date={} value={}>'.format(
                self.account_id, self.transaction_id,
                format_date(self.date),format_value(self.value))

    def __eq__(self, other):
        self_id = self.account_id, self.transaction_id
        other_id = other.account_id, other.transaction_id
        return self_id == other_id


    def show(self, indent=''):
        print("{}Date:    {}".format(indent, format_date(self.date)))
        print("{}Value:   {}".format(indent, format_value(self.value)))
        print("{}Bank:    {}".format(indent, self.bank.title))
        print("{}Account: {}".format(indent, self.account_id))

        if len(self.description) < (79 - len(indent) - 13):
            print("{}Description: {}".format(indent, self.description))
        else:
            description = textwrap.wrap(
                    self.description,
                    initial_indent=indent+'  ', subsequent_indent=indent+'  ')

            print("{}Description:".format(indent))
            print('\n'.join(description))

    def assign(self, session, accounts):
        assert sum(accounts.values()) == self.value

        for name, value in accounts.items():
            account = get_account(session, name)
            payment = BankPayment(account, self, value)
            session.add(payment)

        self.status = 'assigned'
        session.add(self)

    def ignore(self, session):
        self.status = 'ignored'
        session.add(self)



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
    except banking.LoginError as error:
        session.rollback()
        raise LoginError(error.bank, error.username, error.password)
    except:
        session.rollback()
        raise
    finally:
        session.close()

def update_accounts(session):
    for account in get_accounts(session):
        account.update(session)

    for savings in get_savings(session):
        savings.update(session)

def get_account(session, name):
    try:
        return session.query(Account).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchAccount(name)

def get_accounts(session):
    return session.query(Account).all()

def get_num_accounts(session):
    return session.query(Account).count()

def account_exists(session, name):
    return session.query(Account).filter_by(name=name).count() > 0

def get_unknown_accounts(session, names):
    return [x for x in names if not account_exists(session, x)]

def get_bank(session, name):
    try:
        return session.query(Bank).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchBank(name)

def get_banks(session):
    return session.query(Bank).all()

def get_num_banks(session):
    return session.query(Bank).count()

def get_known_bank_names():
    return Bank.modules.keys()

def bank_exists(session, name):
    return session.query(Bank).filter_by(name=name).count() > 0

def get_savings(session):
    return []

def get_new_receipts(session):
    receipts = []
    banks = session.query(Bank).all()

    for bank in banks:
        query = session.query(BankReceipt)
        query = query.filter_by(bank=bank, status='unassigned')
        receipts += query.all()

    return receipts


def parse_budget(budget):
    # If an exception is raised, it is guaranteed to be a ValueError.
    value_str, frequency_str = budget.split()
    return to_cents(value_str), Frequency(frequency_str)

def format_date(date):
    return date.strftime('%m/%d/%y')

def format_value(value):
    if value < 0:
        value = abs(value)
        return '-${}.{:02d}'.format(value // 100, value % 100)
    else:
        return '${}.{:02d}'.format(value // 100, value % 100)

def to_cents(dollars):
    # The input to this function will either be a float or a string.  If it's a 
    # string, remove any dollar signs before further processing.
    try: dollars.replace('$', '')
    except AttributeError: pass
    return int(100 * float(dollars))

def today():
    """ Return today's date.  This function is important because it allows the 
    different dates to be used during testing.  It's also convenient. """
    return datetime.date.today()


class AskForUsername (Exception):
    def __init__(self, bank):
        self.bank = bank

class AskForPassword (Exception):
    def __init__(self, bank):
        self.bank = bank

class NoSuchAccount (Exception):
    def __init__(self, name):
        self.name = name

class NoSuchBank (Exception):
    def __init__(self, name):
        self.name = name

class UnknownFrequency (ValueError):
    def __init__(self, frequency):
        self.frequency = frequency

