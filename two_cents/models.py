#!/usr/bin/env python3

import re

from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE
from django.utils import timezone

from datetime import datetime
from model_utils.managers import InheritanceManager

registered_models = []

class Model(models.Model):

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """
        Create 'boxcar_case' table names from 'CamelCase' class names.
        """
        words = re.findall('([A-Z][a-z0-9]*)', cls.__name__)
        name = '_'.join(('two_cents', *words)).lower()
        cls.Meta = type('Meta', (), dict(db_table=name))

        if kwargs.get('register', True):
            registered_models.append(cls)

## Core tables:

class Budget(Model):
    users = models.ManyToManyField(User, through='BudgetUser')
    title = models.CharField(max_length=255)
    balance = models.FloatField()
    allowance = models.FloatField()
    last_update = models.DateTimeField()
    ui_order = models.IntegerField()

    def __str__(self):
        return self.title

class BudgetUser(Model):
    user = models.ForeignKey(User, on_delete=CASCADE)
    budget = models.ForeignKey(Budget, on_delete=CASCADE)

class Account(Model):
    title = models.CharField(max_length=255)
    balance = models.FloatField()
    last_digits = models.CharField(max_length=64)
    ignore = models.BooleanField()
    ui_order = models.IntegerField()
    objects = InheritanceManager()

    def __str__(self):
        return self.title

    def is_owned_by(self, user):
        raise NotImplementedError

class Transaction(Model):
    objects = InheritanceManager()

    date = models.DateTimeField()
    amount = models.FloatField()
    description = models.CharField(max_length=255)
    budgets = models.ManyToManyField(Budget, through='TransactionBudget')

    # True if the transaction has been fully assigned, i.e. if the sum of the 
    # amounts of all the assignments relating to this transaction equals the 
    # amount of this transaction.  Strictly speaking this field is redundant, 
    # but it's important to be able to access this information quickly.
    fully_assigned = models.BooleanField()

    def __str__(self):
        return f'{self.amount} ({self.remote_id})'

class TransactionBudget(Model):
    # A single transaction can be assigned to multiple budgets, e.g. if you 
    # bought dinner and groceries in one trip to the supermarket, you could 
    # split that transaction between two different budgets.
    budget = models.ForeignKey(Budget, on_delete=CASCADE)
    transaction = models.ForeignKey(Transaction, on_delete=CASCADE)
    amount = models.FloatField()

## Plaid tables:

class PlaidCredential(Model):
    """
    A single credential at a financial institution.
    """
    user = models.ForeignKey(
            User,
            related_name='plaid_credential_set',
            on_delete=CASCADE,
    )
    title = models.CharField(max_length=255)
    last_update = models.DateTimeField()
    ui_order = models.IntegerField()

    # The access_token will allow us to make authenticated calls to the Plaid 
    # API.  The item_id is used to identify the credential in webhooks.
    plaid_access_token = models.CharField(max_length=64)
    plaid_item_id = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return f'{self.title} ({self.plaid_item_id})'

class PlaidAccount(Account):
    """
    Represents a single account (e.g. checking, savings, credit, etc.).

    There can be multiple accounts per credential.  There can also be multiple 
    credentials per account (i.e. if you have a joint account, all parties will 
    be able to access that account using their own credentials).
    """
    remote_id = models.CharField(max_length=64, unique=True)
    credentials = models.ManyToManyField(
            PlaidCredential,
            through='PlaidAccountCredential',
            related_name='plaid_account_set',
    )

    def __str__(self):
        return f'{self.title} ({self.remote_id})'

    def is_owned_by(self, user):
        return any(user == cred.user for cred in self.credentials.all())


class PlaidAccountCredential(Model):
    """
    There is a many-to-many relationship between Plaid credentials and accounts:

    - One credential can obviously access multiple accounts (e.g. checking, 
      savings, credit, etc.)
    - Jointly owned accounts can be accessed using multiple credentials.
    """
    credential = models.ForeignKey(PlaidCredential, on_delete=CASCADE)
    account = models.ForeignKey(PlaidAccount, on_delete=CASCADE)

class PlaidTransaction(Transaction):
    remote_id = models.CharField(max_length=64, unique=True)
    account = models.ForeignKey(PlaidAccount, on_delete=CASCADE)

## OFX tables:

class OfxAccount(Account):
    remote_id = models.IntegerField()
    user = models.ForeignKey(User, on_delete=CASCADE)
    last_update = models.DateTimeField()

    def is_owned_by(self, user):
        return user == self.user

class OfxTransaction(Transaction):
    remote_id = models.IntegerField()
    account = models.ForeignKey(OfxAccount, on_delete=CASCADE)

## Helper functions:

def get_plaid_client():
    import plaid
    from two_cents import secrets

    return plaid.Client(
            client_id=secrets.PLAID_CLIENT_ID,
            secret=secrets.PLAID_SECRET,
            public_key=secrets.PLAID_PUBLIC_KEY,
            environment=secrets.PLAID_ENVIRONMENT,
    )

def get_plaid_credential(user):
    return PlaidCredential.objects.filter(user=user).order_by('ui_order')

def get_plaid_credential_from_webhook(item_id):
    return PlaidCredential.objects.get(plaid_item_id=item_id)

def get_plaid_account(remote_id):
    return PlaidAccount.objects.get(remote_id=remote_id)


def get_transactions(user):
    # Not this simple; need to separately get Plaid and OFX transactions, 
    # because the two have different logic for determining ownership.
    pass
    # return Transaction.objects.filter(user=user)

def sync_transactions(credential):
    client = get_plaid_client()
    now = timezone.now()
    response = client.Transactions.get(
            access_token=credential.plaid_access_token,
            start_date='{:%Y-%m-%d}'.format(credential.last_update),
            end_date='{:%Y-%m-%d}'.format(now),
    )
    pprint(response)

    for fields in response['transactions']:
        transaction = PlaidTransaction.objects.get_or_create(
                remote_id=fields['account_id'],
                defaults=dict(
                    account=get_plaid_account(fields['account_id']),
                    date=datetime.strptime(fields['date'], '%Y-%m-%d'),
                    amount=-float(fields['amount']),
                    description=fields['name'],
                    fully_assigned=False,
                ),
        )

    credential.last_update = now
    credential.save()

    return response


def get_assignments(txn):
    return TransactionBudget.objects.query(transaction=txn)
