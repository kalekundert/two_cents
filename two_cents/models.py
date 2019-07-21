#!/usr/bin/env python3

import re

from django.db import models
from django.contrib.auth.models import User
from django.db.models import CASCADE
from django.utils import timezone

from datetime import datetime, timedelta
from model_utils.managers import InheritanceManager
from pprint import pprint

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

class Family(Model):
    users = models.ManyToManyField(User, through='FamilyUser')

    # Indicate that this particular family represents just the user.  A 
    # so-called "personal" family is automatically created for each user when 
    # they sign up.  It cannot be deleted, and new members cannot be added.
    is_personal = models.BooleanField()

    # Users can give their own titles to their families, but this is the title 
    # to use if the user hasn't specified anything.  It is set when the family 
    # is created in the first place, and cannot be modified.
    default_title = models.CharField(max_length=255)

    def __str__(self):
        return ', '.join(u.username for u in self.users.all())

    def get_title(self, user):
        link = FamilyUser.filter(family=self, user=user).get()
        return link.title

class FamilyUser(Model):
    user = models.ForeignKey(User, on_delete=CASCADE)
    family = models.ForeignKey(Family, on_delete=CASCADE)
    custom_title = models.CharField(max_length=255, null=True)
    ui_order = models.IntegerField()

    @property
    def title(self):
        return self.custom_title or self.family.default_title

class Bill(Model):
    family = models.ForeignKey(Family, on_delete=CASCADE)
    title = models.CharField(max_length=255)
    expense = models.FloatField()
    ui_order = models.IntegerField()

    def __str__(self):
        return f"Budget(family={self.family}, title={self.title}, expense={self.expense})"

class Budget(Model):
    family = models.ForeignKey(Family, on_delete=CASCADE)
    title = models.CharField(max_length=255)
    balance = models.FloatField()
    allowance = models.FloatField()
    last_update = models.DateTimeField()
    ui_order = models.IntegerField()

    def __str__(self):
        return f'Budget "{self.title}" for "{self.family}"'

class Account(Model):
    family = models.ForeignKey(Family, on_delete=CASCADE)
    title = models.CharField(max_length=255)
    balance = models.FloatField()
    last_digits = models.CharField(max_length=64)
    ignore = models.BooleanField()
    ui_order = models.IntegerField()

    objects = InheritanceManager()

    def __str__(self):
        return f'Account "{self.title}" for "{self.family}"'

class Transaction(Model):
    account = models.ForeignKey(Account, on_delete=CASCADE)
    date = models.DateTimeField()
    amount = models.FloatField()
    description = models.CharField(max_length=255)
    budgets = models.ManyToManyField(Budget, through='TransactionBudget')

    # True if the transaction has been fully assigned, i.e. if the sum of the 
    # amounts of all the assignments relating to this transaction equals the 
    # amount of this transaction.  Strictly speaking this field is redundant, 
    # but it's important to be able to access this information quickly.
    fully_assigned = models.BooleanField()

    objects = InheritanceManager()

    def __str__(self):
        return f'Transaction in {self.account} for "{self.description}" worth "{self.amount}"'

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

## OFX tables:

class OfxAccount(Account):
    remote_id = models.IntegerField()
    last_update = models.DateTimeField()

class OfxTransaction(Transaction):
    remote_id = models.IntegerField()

## Helper functions:

def get_plaid_client():
    import plaid
    from two_cents import settings

    return plaid.Client(
            client_id=settings.PLAID_CLIENT_ID,
            secret=settings.PLAID_SECRET,
            public_key=settings.PLAID_PUBLIC_KEY,
            environment=settings.PLAID_ENVIRONMENT,
    )

def get_plaid_credential(user):
    return PlaidCredential.objects.filter(user=user).order_by('ui_order')

def get_plaid_credential_from_webhook(item_id):
    return PlaidCredential.objects.get(plaid_item_id=item_id)

def get_plaid_account(remote_id):
    return PlaidAccount.objects.get(remote_id=remote_id)


def get_transactions(user):
    return Transaction.objects.filter(account__family__users=user)

def sync_transactions(credential):
    client = get_plaid_client()
    # Go back an extra 30 days to make sure we don't miss anything.
    start_date = credential.last_update - timedelta(days=30)
    end_date = timezone.now()

    response = client.Transactions.get(
            access_token=credential.plaid_access_token,
            start_date='{:%Y-%m-%d}'.format(start_date),
            end_date='{:%Y-%m-%d}'.format(end_date),
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

    credential.last_update = end_date
    credential.save()

    return response


def get_families(user):
    return Family.objects.filter(users=user)

def get_personal_family(user):
    return Family.objects.filter(users=user, is_personal=True).get()

def get_default_family(user):
    return get_personal_family(user)

def get_budgets(user):
    return Budget.objects.filter(family__users=user).order_by('ui_order')

def get_incomes(user):
    return Bill.objects.filter(family__users=user, expense__gt=0).order_by('ui_order')

def get_bills(user):
    return Bill.objects.filter(family__users=user, expense__lt=0).order_by('ui_order')

def get_assignments(txn):
    return TransactionBudget.objects.query(transaction=txn)

def init_user(user):
    # Make a family for the user.
    family = Family.objects.create(
            default_title="Personal",
            is_personal=True,
    )
    FamilyUser.objects.create(
            user=user,
            family=family,
            ui_order=0,
    )

    # Make some default budgets for the user.  They can change or get rid of 
    # these later, but they're a good starting point.
    default_budgets = "Necessities", "Luxuries", "Surprises"

    for i, title in enumerate(default_budgets):
        Budget.objects.create(
                family=family,
                title=title,
                balance=0,
                allowance=0,
                last_update=timezone.now(),
                ui_order=i,
        )

def user_owns_account(user, account):
    return user in account.family.users.all()
