#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def budgets(request):
    # - List budgets
    # - Option to add/delete/rename/reorder/change allowance.
    return render(request, 'two_cents/budgets.html')

