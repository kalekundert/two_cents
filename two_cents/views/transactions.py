#!/usr/bin/env python3

from two_cents import models

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def show(request):
    # - List transactions
    # - Option to assign/reassign.
    # - Option to upload qfx.
    return render(request, 'two_cents/transactions.html', context=dict(
        txns=models.get_transactions(request.user),
        get_assignments=models.get_assignments,
    ))

