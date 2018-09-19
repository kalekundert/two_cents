#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def accounts(request):
    # - List accounts
    # - Option to add (will redirect to plaid)/rename.
    return render(request, 'two_cents/accounts.html')

