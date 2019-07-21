#!/usr/bin/env python3

import json
import functools

from two_cents import models
from two_cents.settings import PLAID_PUBLIC_KEY, PLAID_ENVIRONMENT

from django import forms
from django.http.response import HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied

def validate_account(request):
    try:
        id = int(request.data['account_id'])
        account = models.Account.objects\
            .select_subclasses()\
            .get(id=id)
    except models.Account.DoesNotExist:
        raise NotFound()
    except BaseException as err:
        raise ValidationError(str(err))

    if not models.user_owns_account(request.user, account):
        raise PermissionDenied()

    return account

def require_account(f):
    @functools.wraps(f)
    def wrapper(request):
        account = validate_account(request)
        return f(account)
    return wrapper


@login_required
def show(request):
    # - List accounts
    # - Option to add (will redirect to plaid)/rename.
    return render(request, 'two_cents/accounts.html', context=dict(
        plaid_public_key=PLAID_PUBLIC_KEY,
        plaid_environment=PLAID_ENVIRONMENT,
        webhook_url=request.build_absolute_uri(reverse('2c_banks_sync')),
        banks=models.get_plaid_credential(request.user),
    ))

@api_view(['POST'])
@require_account
def toggle(account):
    account.ignore = not account.ignore
    account.save()
    return Response({
        'account_id': account.id,
        'ignore': account.ignore,
    })

