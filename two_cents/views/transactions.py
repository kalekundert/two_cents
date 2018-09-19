#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def transactions(request):
    # - List transactions
    # - Option to assign/reassign.
    # - Option to upload qfx.
    return render(request, 'two_cents/transactions.html')

