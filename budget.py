#!/usr/bin/env python3

import os
import sqlalchemy
from sqlalchemy.orm import *
from sqlalchemy.types import *
from sqlalchemy.schema import *
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
import datetime
import subprocess
import shlex
import textwrap
import yaml
import scraping
from pprint import pprint

Base = declarative_base()
Cents = Integer
Days = Integer

class Account (Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)

    debits = relationship('Debit', backref='account')
    credits = relationship('Credit', backref='account')
    budgets = relationship('Budget', backref='account')
    filters = relationship('Filter', backref='account')

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<account name={}>'.format(self.name)

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
                


class Debit (Base):
    __tablename__ = 'debits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    bank_id = Column(Integer, ForeignKey('banks.id'))

    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)
    initial_value = Column(Cents, nullable=False)
    description = Column(Text)

    def __init__(self, date, description, initial_value):
        self.date = date
        self.description = description
        self.value = initial_value
        self.initial_value = initial_value

    def __repr__(self):
        date = self.date.strftime('%m/%d/%y')
        value = '${}.{:02d}'.format(self.value // 100, self.value % 100)
        return '<debit date={} value={}>'.format(date, value)

    def show(self, indent=''):
        date = self.date.strftime('%m/%d/%y')
        value = '${}.{:02d}'.format(self.value // 100, self.value % 100)
        bank = self.bank.title

        print("{}Date:  {}".format(indent, date))
        print("{}Value: {}".format(indent, value))
        print("{}Bank:  {}".format(indent, bank))

        if len(self.description) < (79 - len(indent) - 13):
            print("{}Description: {}".format(indent, self.description))
        else:
            description = textwrap.wrap(
                    self.description,
                    initial_indent=indent+'  ', subsequent_indent=indent+'  ')

            print("{}Description:".format(indent))
            print('\n'.join(description))

    def assign(self, accounts):
        pass


class Credit (Base):
    __tablename__ = 'credits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), primary_key=True)

    date = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)
    initial_value = Column(Cents, nullable=False)
    max_lifetime = Column(Days)
    description = Column(Text)

    forever = 0

    def __init__(self, account, value, date):
        self.account = account
        self.date = date
        self.initial_value = self.value = value

    def __repr__(self):
        return '<credit value={}>'.format(self.value)

    def prune(self, session):
        if self.max_lifetime == Credit.forever:
            return

        current_age = datetime.date.today() - self.date
        if current_age.days > self.max_lifetime:
            session.delete(self)


class Budget (Base):
    __tablename__ = 'budgets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), primary_key=True)

    last_updated = Column(Date, nullable=False)
    daily_allowance = Column(Cents, nullable=False)
    credit_duration = Column(Days, nullable=False)

    def __repr__(self):
        return '<budget account={} allowance={}>'.format(
                self.account.id, self.daily_allowance)

    def update(self, session):
        today = datetime.date.today()
        days_behind = (today - self.last_updated).days
        one_day = datetime.timedelta(days=1)
        credit_date = self.last_updated

        for i in range(days_behind):
            credit_date += one_day
            credit = Credit(self.account, credit_date, self.daily_allowance)
            session.add(credit)

        self.last_updated = today
        session.add(self)


class Savings (Base):
    __tablename__ = 'savings'

    id = Column(Integer, primary_key=True, autoincrement=True)

    last_updated = Column(Date, nullable=False)
    value = Column(Cents, nullable=False)
    frequency = Column(Days, nullable=False)

class Bank (Base):
    __tablename__ = 'banks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    username_raw = Column(String)
    username_command = Column(String)
    password_raw = Column(String)
    password_command = Column(String)
    last_state = Column(Text, default=yaml.dump({}), nullable=False)

    filters = relationship('Filter', backref='bank')
    debits = relationship('Debit', backref='bank')

    #CheckConstraint('username_raw is not null or username_command is not null')
    #CheckConstraint('password_raw is not null or password_command is not null')

    def __init__(self, name):
        self.name = name
        self.last_update = datetime.date.today()

    def update(self, session):
        state = yaml.load(self.last_state)
        scraper_class = scraping.modules[self.name]
        scraper = scraper_class(self.username, self.password, state)

        new_debits = scraper.download()
        for debit in new_debits: debit.bank = self

        self.last_state = yaml.dump(state)
        session.add(self)

        return new_debits

    @property
    def title(self):
        return scraping.modules[self.name].title

    @property
    def username(self):
        if self.username_command:
            command = shlex.split(self.username_command)
            return subprocess.check_output(command)
        else:
            return self.username_raw

    @property
    def password(self):
        if self.password_command:
            command = shlex.split(self.password_command)
            return subprocess.check_output(command)
        else:
            return self.password_raw


class Filter (Base):
    __tablename__ = 'filters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey('banks.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))

    pattern = Column(String, nullable=False)


class FatalError (BaseException):

    def handle(self):
        raise self


class LoginError (FatalError):

    def __init__(self, bank, username, password):
        self.bank = bank
        self.username = username
        self.password = password

    def handle(self):
        try:
            print('Unable to login to {}.'.format(self.bank))
            print('User name: {}   Password: {}   (Ctrl-C to clear)'.\
                    format(self.username, self.password)[:79], end='')
            input()

        except (KeyboardInterrupt, EOFError):
            print('\r' + 79 * ' ')



@contextmanager
def open_db():
    try:
        # Create a new session.
        url = 'sqlite:///' + os.path.expanduser('~/.config/budget/budget.db')
        engine = sqlalchemy.create_engine(url)
        session = sqlalchemy.orm.sessionmaker(bind=engine)()

        # Make sure the database is properly set up.
        Base.metadata.create_all(engine)
        if not get_accounts(session):
            account = Account('unassigned')
            session.add(account)

        # Return the session.
        yield session
        session.commit()
    except KeyboardInterrupt:
        session.rollback()
        print()
    except EOFError:
        session.rollback()
        print()
    except FatalError as error:
        session.rollback()
        error.handle()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def get_banks(session):
    return session.query(Bank).all()
def get_account(session, name):
    return session.query(Account).filter_by(name=name).one()

def get_accounts(session):
    return session.query(Account).all()

def get_holding_area(session):
    return session.query(Account).filter_by(name='unassigned').one()

def get_unassigned_debits(session):
    return get_holding_area(session).debits

def get_debits(session):
    return session.query(Debits).all()

def get_savings(session):
    return session.query(Savings).all()

