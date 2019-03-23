#!/usr/bin/env python3

from django.shortcuts import render, redirect

def show(request):
    if request.user.is_authenticated:
        # - If there are unassigned transactions, ask to assign them
        # - Display balances
        return render(request, "two_cents/dashboard.html")
    else:
        # - Log-in/sign-up form
        # - Briefly describe philosophy
        return render(request, "two_cents/home.html")

