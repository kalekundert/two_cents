#!/usr/bin/env python3

from two_cents import models

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory

@login_required
def show(request):
    # - List transactions
    # - Option to assign/reassign.
    # - Option to upload qfx.

    forms = TransactionForms(request)
    forms.handle_post()

    return render(request, 'two_cents/transactions.html', context=locals())

class TransactionForms:

    AssignmentFormset = inlineformset_factory(
            models.Transaction,
            models.TransactionBudget,
            fields=['budget', 'amount'],
            extra=1,
    )

    def __init__(self, request):
        self.request = request
        self.transactions = []
        self.forms = {}

        self.make_forms(request.POST or None)

    def __iter__(self):
        for txn in self.transactions:
            yield txn, self.forms[txn.id]

    def make_forms(self, data):
        self.transactions = models.get_transactions(self.request.user)
        self.forms = {}

        for txn in self.transactions:
            self.forms[txn.id] = self.AssignmentFormset(
                    data,
                    instance=txn,
                    prefix=f'txn-{txn.id}-',
            )

    def handle_post(self):
        # Don't do anything if the form wasn't submitted:
        if not self.request.method == 'POST':
            return

        # Don't do anything if the form has errors:
        any_errors = any(not x.is_valid() for x in self.forms.values())
        if any_errors:
            return

        # Save the transaction assignment.
        for form in self.forms.values():
            x = form.save()
            print(form.instance)
            print(x)
            print()

        # Make a new form, so that the information that was just saved will be 
        # up-to-date when the page reloads.
        self.make_forms(None)

