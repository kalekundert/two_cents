#!/usr/bin/env python3

import re
from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE

registered_models = []

class Model(models.Model):

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass__(cls, **kwargs):
        words = re.findall('([A-Z][a-z0-9]*)', cls.__name__)
        name = '_'.join(('two_cents', *words)).lower()
        cls.Meta = type('Meta', (), dict(db_table=name))

        if kwargs.get('register', True):
            registered_models.append(cls)



class Account(Model):
    # An account can be owned by multiple users, e.g. a joint bank account.
    users = models.ManyToManyField(User, through='AccountUser')
    title = models.CharField(max_length=255)
    last_update = models.DateTimeField()
    order = models.IntegerField()

class AccountUser(Model):
    STATUS_CHOICES = (
            ('confirmed', 'Confirmed'),
            ('invited', 'Invited'),
            ('requested', 'Requested'),
    )
    account = models.ForeignKey(Account, on_delete=CASCADE)
    user = models.ForeignKey(User, on_delete=CASCADE)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES)


class AccountPlaid(Model):
    # Keep the plaid details in their own table, so the schema isn't tightly 
    # coupled to a single integration.  For example, I might want to allow 
    # users to manually upload *.qfx files (that way, they won't need to trust 
    # anyone with their bank login credentials).
    account = models.OneToOneField(Account, on_delete=CASCADE)
    access_token = models.CharField(max_length=32)
    item_id = models.CharField(max_length=32)


class Budget(Model):
    # Transactions can only be assigned to budgets 
    users = models.ManyToManyField(User, through='BudgetUser')
    title = models.CharField(max_length=255)
    balance = models.FloatField()
    allowance = models.FloatField()
    last_update = models.DateTimeField()
    order = models.IntegerField()

class BudgetUser(Model):
    user = models.ForeignKey(User, on_delete=CASCADE)
    budget = models.ForeignKey(Budget, on_delete=CASCADE)

class Transaction(Model):
    account = models.ForeignKey(Account, on_delete=CASCADE)
    budgets = models.ManyToManyField(Budget, through='TransactionBudget')
    date = models.DateTimeField()
    format = models.CharField(max_length=255)
    amount = models.FloatField()
    category = models.CharField(max_length=255)
    description = models.CharField(max_length=255)

    # True if the transaction has been fully assigned, i.e. if the sum of the 
    # amounts of all the assignments relating to this transaction equals the 
    # amount of this transaction.  Strictly speaking this field is redundant, 
    # but it's important to be able to access this information quickly.
    assigned = models.BooleanField()


class TransactionBudget(Model):
    # A single transaction can be assigned to multiple budgets, e.g. if you 
    # bought dinner and groceries in one trip to the supermarket, you could 
    # split that transaction between two different budgets.
    budget = models.ForeignKey(Budget, on_delete=CASCADE)
    transaction = models.ForeignKey(Transaction, on_delete=CASCADE)
    amount = models.FloatField()

# Work in progress: Automatically categorize certain transactions.
class Filters:
    pass
class FilterCategory:
    pass
class FilterMerchant:
    pass
class FilterLearning:
    pass
