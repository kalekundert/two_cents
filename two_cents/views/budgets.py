#!/usr/bin/env python3

from two_cents import models
from pprint import pprint

from django import forms
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required as require_login
from django.views.decorators.http import require_POST as require_post
from django.forms import modelformset_factory, ModelChoiceField
from django.forms.widgets import HiddenInput
from django.utils import timezone

@require_login
def show(request):
    # - List budgets
    # - Option to add/delete/rename/reorder/change allowance.

    forms = {
            'bill': BillForm(
                    request,
                    prefix='bill',
                    queryset=models.get_bills_and_incomes(request.user),
            ),
            'budget': BudgetForm(
                    request,
                    prefix='budget',
                    queryset=models.get_budgets(request.user),
            ),
    }
    pprint(request.POST)

    #for form in forms.values():
        #form.handle_post()

    return render(request, 'two_cents/budgets.html', context=locals())

class FormsetWrapper:

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

class BillForm(FormsetWrapper):

    def make_form(self, post, **kwargs):
        formset_cls = modelformset_factory(
                model=models.Bill,
                fields=['title', 'expense', 'ui_order'],
                widgets={
                    'title': forms.TextInput(attrs={'class': 'title'}),
                    'expense': forms.TextInput(attrs={'class': 'allowance'}),
                    'ui_order': forms.HiddenInput(),
                },
                can_delete=True,
        )
        return formset_cls(post, **kwargs)

    def save_form(self):
        bills = self.formset.save(commit=False)

        for i, bill in enumerate(bills):
            bill.ui_order = i
            bill.save()

class BudgetForm(FormsetWrapper):

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

class FamilyChoiceField(ModelChoiceField):
    """
    Allow the user to select one of their families.

    If the user only has their personal family, no choice is presented and that 
    family is returned to the backend as a hidden form element.  If the user 
    does have families to choose between, those families are presented as a 
    dropdown box.

    Note that this field requires that the user object be given as an argument 
    to the constructor.  This more or less requires that the whole form (or 
    formset) be assembled directly in the view, rather than at module scope.
    """

    def __init__(self, user):
        self.user = user

    def __call__(self, **kwargs):
        super().__init__(
                initial=models.get_default_family(self.user),
                **kwargs
        )

        if len(kwargs['queryset']) == 1:
            self.widget = HiddenInput()

        return self

    def label_from_instance(self, family):
        return family.get_title(self.user)


