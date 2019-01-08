#!/usr/bin/env python3

import re
from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE

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



class Bank(Model):
    """
    Represents a single credential at a financial institution.
    """
    user = models.ForeignKey(User, on_delete=CASCADE)
    title = models.CharField(max_length=255)
    last_update = models.DateTimeField()
    ui_order = models.IntegerField()

    # The access_token will allow us to make authenticated calls to the Plaid 
    # API.  The item_id is used to identify Items in webhooks.
    plaid_item_id = models.CharField(max_length=64, unique=True)
    plaid_access_token = models.CharField(max_length=64)

    def __str__(self):
        return f'{self.title} ({self.plaid_item_id})'

class Account(Model):
    """
    Represents a single account (e.g. checking, savings, credit, etc.).

    There can be multiple accounts per credential.  There can also be multiple 
    credentials per account (i.e. if you have a joint account, all parties will 
    be able to access that account using their own credentials).
    """
    remote_id = models.CharField(max_length=64, unique=True)
    banks = models.ManyToManyField(Bank, through='AccountBank')
    title = models.CharField(max_length=255)
    last_digits = models.CharField(max_length=64)
    ui_order = models.IntegerField()

    def __str__(self):
        return f'{self.title} ({self.remote_id})'

class AccountBank(Model):
    bank = models.ForeignKey(Bank, on_delete=CASCADE)
    account = models.ForeignKey(Account, on_delete=CASCADE)

class Budget(Model):
    # Transactions can only be assigned to budgets, not users.
    user = models.ForeignKey(User, on_delete=CASCADE)
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

class Transaction(Model):
    remote_id = models.CharField(max_length=64, unique=True)
    account = models.ForeignKey(Account, null=True, on_delete=CASCADE)
    budgets = models.ManyToManyField(Budget, through='TransactionBudget')
    date = models.DateTimeField()
    amount = models.FloatField()
    description = models.CharField(max_length=255)

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

def get_plaid_client():
    import plaid
    from two_cents import secrets

    return plaid.Client(
            client_id=secrets.PLAID_CLIENT_ID,
            secret=secrets.PLAID_SECRET,
            public_key=secrets.PLAID_PUBLIC_KEY,
            environment=secrets.PLAID_ENVIRONMENT,
    )

def bank_from_webhook(item_id):
    return Bank.objects.get(plaid_item_id=item_id)

def sync_transactions(bank):
    client = get_plaid_client()
    response = client.Transactions.get(
            access_token=bank.plaid_access_token,
            start_date='{:%Y-%m-%d}'.format(bank.last_update),
            end_date='{:%Y-%m-%d}'.format(datetime.now()),
    )

    for fields in response['tranactions']:
        transaction = Transaction.objects.create(
                remote_id=fields['account_id'],
                account=Account.get(remote_id=fields['account_id']),
                date=datetime.strptime(fields['date'], '%Y-%m-%d'),
                amount=-float(fields['amount']),
                description=fields['name'],
                assigned=False,
        )

    return response

