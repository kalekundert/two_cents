#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required as require_login
from django.views.decorators.http import require_POST as require_post
from django import forms
from django.forms import modelformset_factory
from two_cents import models
from two_cents.forms import FamilyChoiceField

@require_login
def show(request):
    # - List budgets
    # - Option to add/delete/rename/reorder/change allowance.

    forms = {
            'income': BillFormWrapper(
                    request,
                    prefix='income',
                    queryset=models.get_incomes(request.user),
            ),
            'bill': BillFormWrapper(
                    request,
                    prefix='bill',
                    queryset=models.get_bills(request.user),
            ),
            'budget': BudgetFormWrapper(
                    request,
                    prefix='budget',
                    queryset=models.get_budgets(request.user),
            ),
    }

    for form in forms.values():
        form.handle_post()

    return render(request, 'two_cents/budgets.html', context=locals())

class FormWrapper:

    def __init__(self, request, **kwargs):
        self.request = request
        self.kwargs = kwargs
        self.formset = self.make_form(request.POST or None, **kwargs)

    def __iter__(self):
        yield from self.formset

    def __str__(self):
        return str(self.formset)

    def handle_post(self):
        # Don't do anything if the form wasn't submitted:
        if not self.request.method == 'POST':
            return

        # If the form has errors, stop and send the errors back to the user.
        if not self.formset.is_valid():
            return

        # Update the database
        self.save_form()

        # Reset the form (i.e. so items that were added or deleted last time 
        # won't be added or deleted again).
        self.formset = self.make_form(None, **self.kwargs)

    def make_form(self, data):
        raise NotImplementedError

    def save_form(self):
        self.formset.save()

class BillFormWrapper(FormWrapper):

    def make_form(self, post, **kwargs):
        formset_cls = modelformset_factory(
                model=models.Bill,
                fields=['family', 'title', 'expense'],
                field_classes={'family': FamilyChoiceField(self.request.user)},
        )
        return formset_cls(post, **kwargs)

    def save_form(self):
        bills = self.formset.save(commit=False)

        print(bills)
        for i, bill in enumerate(bills):
            bill.ui_order = i
            bill.save()

class BudgetFormWrapper(FormWrapper):

    def make_form(self, post, **kwargs):
        formset_cls = modelformset_factory(
                model=models.Budget,
                fields=['family', 'title', 'allowance', 'balance'],
                field_classes={'family': FamilyChoiceField(self.request.user)},
        )
        return formset_cls(post, **kwargs)

    def save_form(self):
        budgets = self.formset.save(commit=False)

        for budget in self.formset.new_objects:
            budget.last_update = timezone.now()

        for i, budget in enumerate(budgets):
            budget.ui_order = i
            budget.save()


