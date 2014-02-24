#!/usr/bin/env python3

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

Base = declarative_base()
Cents = Integer
Days = Integer
Rate = String

class Account (Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    value = Column(Cents, nullable=False)

    payments = relationship('Payment', backref='account')
    allowances = relationship('Allowance', backref='account')
    filters = relationship('Filter', backref='account')

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

    def update(self):
        key = lambda credit: (credit.max_lifetime == 0, credit.days_remaining)
        self.credits.sort(key=key)

        # Get rid of any expired credits.

        for credit in self.credits:
            credit.prune()

        # Update any budgets linked to this account.

        for budget in self.budgets:
            budget.update()

        # Pay off as many debits as possible.

        for debit in self.debits:
            for credit in self.credits:
                debit.value -= credit.value
                credit.value -= debit.value

                if debit.value <= 0:
                    session.delete(debit); break
                if credit.value <= 0:
                    session.delete(credit)
                


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


class Allowance (Base):
    __tablename__ = 'allowances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), primary_key=True)

    update_value = Column(Cents, nullable=False)
    update_frequency = Column(Rate, nullable=False)
    last_updated = Column(Date, nullable=False)

    def __init__(self, account, value, frequency='daily'):
        self.account = account
        self.update_value = value
        self.update_frequency = frequency
        self.last_updated = datetime.date.today()

    def __repr__(self):
        return '<budget id={} account={} value={} {}>'.format(
                self.id, self.account.id,
                self.update_value, self.update_frequency)

    def update(self, session):
        credit = self.update_value * num_updates_due(self)
        self.account.value += credit
        self.last_updated = today
        session.add_all([self, self.account])


class AllowancePayment (Payment):
    __tablename__ = 'allowance_payments'

    id = Column(Integer, ForeignKey('payments.id'), primary_key=True)
    allowance_id = Column(Integer, ForeignKey('allowances.id'))

class Savings (Base):
    __tablename__ = 'savings'

    id = Column(Integer, primary_key=True, autoincrement=True)

    update_value = Column(Cents, nullable=False)
    update_frequency = Column(Rate, nullable=False)
    last_updated = Column(Date, nullable=False)

    def __init__(self, value, frequency='monthly'):
        self.update_value = value
        self.update_frequency = frequency

    def __repr__(self):
        return '<savings id={} value={} {}>'.format(
                self.id, self.update_value, self.update_frequency)


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
    filters = relationship('Filter', backref='bank')

    modules = {
            'wells-fargo': banking.WellsFargo
    }

    def __init__(self, name, username_command, password_command):
        self.name = name
        self.username_command = username_command
        self.password_command = password_command
        self.last_update = datetime.date.today()

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


class Filter (Base):
    __tablename__ = 'filters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey('banks.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))
    pattern = Column(String, nullable=False)

    def __repr__(self):
        return '<filter id={} bank_id={} account_id={} pattern={}>'.format(
                self.id, self.bank_id, self.account_id, self.pattern)



@contextmanager
def open_db():
    try:
        # Create a new session.
        url = 'sqlite:///' + os.path.expanduser('~/.config/budget/budget.db')
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

def get_account(session, name):
    try:
        return session.query(Account).filter_by(name=name).one()
    except sqlalchemy.orm.exc.NoResultFound:
        raise NoSuchAccount(name)

def get_accounts(session):
    return session.query(Account).all()

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

def get_known_bank_names():
    return Bank.modules.keys()

def bank_exists(session, name):
    return session.query(Bank).filter_by(name=name).count() > 0

def get_new_receipts(session):
    receipts = []
    banks = session.query(Bank).all()

    for bank in banks:
        query = session.query(BankReceipt)
        query = query.filter_by(bank=bank, status='unassigned')
        receipts += query.all()

    return receipts


def format_date(date):
    return date.strftime('%m/%d/%y')

def format_value(value):
    if value < 0:
        value = abs(value)
        return '-${}.{:02d}'.format(value // 100, value % 100)
    else:
        return '${}.{:02d}'.format(value // 100, value % 100)

def to_cents(dollars):
    return int(100 * float(dollars))

def is_update_due(budget):
    return False

def require_accounts(session):
    if session.query(Account).count() == 0:
        raise NoAccounts()

def require_banks(session):
    if session.query(Bank).count() == 0:
        raise NoBanks()


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
class NoAccounts (Exception):
    pass

class NoBanks (Exception):
    pass

