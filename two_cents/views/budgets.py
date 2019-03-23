#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required as require_login
from django.views.decorators.http import require_POST as require_post
from django import forms
from two_cents import models

class BudgetForm(forms.ModelForm):
    class Meta:
        model = models.Budget
        fields = 'title', 'allowance'

@require_login
def show(request):
    # - List budgets
    # - Option to add/delete/rename/reorder/change allowance.
    budgets = [{
            'model': b,
            'form': BudgetForm(instance=b, prefix=b.id),
        } for b in models.get_budgets(request.user)
    ]
    add_budget_form = BudgetForm()

    return render(request, 'two_cents/budgets.html', context=locals())

@require_login
@require_post
def add(request):
    form = BudgetForm(request.POST)
    if form.is_valid():
        form.save()

    return redirect('2c_budgets')

@require_login
@require_post
def update(request):
    pass

