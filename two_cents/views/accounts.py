#!/usr/bin/env python3

import json
from datetime import datetime
from nonstdlib.debug import log, debug, info, warn, error, critical, fatal

from django.http.response import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from two_cents import models
from two_cents.secrets import PLAID_PUBLIC_KEY

@login_required
def accounts(request):
    # - List accounts
    # - Option to add (will redirect to plaid)/rename.
    banks=models.Bank.objects.filter(user=request.user).order_by('ui_order')
    return render(request, 'two_cents/accounts.html', context=dict(
        plaid_public_key=PLAID_PUBLIC_KEY,
        banks=banks,
    ))

@login_required
@require_POST
def add_bank(request):
    """
    This method is triggered when a user successfully completes the Plaid Link 
    form.
    """

    # An example of the data that will be posted to us by Plaid Link:
    # {'account': {'id': 'yBwD4KxGDWcBplWKKWqKHwV4G5rggzhyyEZ5L',
    #              'mask': '0000',
    #              'name': 'Plaid Checking',
    #              'subtype': 'checking',
    #              'type': 'depository'},
    #  'account_id': 'yBwD4KxGDWcBplWKKWqKHwV4G5rggzhyyEZ5L',
    #  'accounts': [{'id': 'yBwD4KxGDWcBplWKKWqKHwV4G5rggzhyyEZ5L',
    #                'mask': '0000',
    #                'name': 'Plaid Checking',
    #                'subtype': 'checking',
    #                'type': 'depository'},
    #               {'id': 'nWvbyDoZbQh8bnWppWApCqP5lMJRRjT66zXED',
    #                'mask': '1111',
    #                'name': 'Plaid Saving',
    #                'subtype': 'savings',
    #                'type': 'depository'}],
    #  'institution': {'institution_id': 'ins_3', 'name': 'Chase'},
    #  'link_session_id': 'fbe4b241-a285-4041-82fa-68890d37b85c',
    #  'public_token': 'public-sandbox-fdb2b881-7d34-42e8-ae9f-44d5ae7075d5'},

    post = json.loads(request.body)
    pprint(post)

    client = models.get_plaid_client()
    exchange = client.Item.public_token.exchange(post['public_token'])

    bank = models.Bank.objects.create(
            user=request.user,
            title=post['institution']['name'],
            last_update=datetime.now(),
            ui_order=request.user.bank_set.count(),
            plaid_item_id=exchange['item_id'],
            plaid_access_token=exchange['access_token'],
    )

    for i, fields in enumerate(post['accounts']):
        account = models.Account.objects.create(
                remote_id=fields['id'],
                title=fields['name'],
                last_digits=fields['mask'],
                ui_order=i,
        )
        models.AccountBank.objects.create(
                bank=bank,
                account=account,
        )

    return redirect('2c_home')

@require_POST
@csrf_exempt
def sync_bank(request):
    # Plaid will POST to this URL when it downloads new transaction data for an 
    # account.  (The webhook is configured by Plaid Link when the user first 
    # links to their bank.)
    #
    # Note that the request just contains the `item_id` of the account in 
    # question.  It doesn't contain any transaction data, or even any 
    # authenticating information.  So we need to react to the request by 
    # querying Plaid for the actual data and updating our model.

    try:
        post = json.loads(request.body)
    except:
        #return bad_request(f"Expected POST to contain JSON formatted data, not: {request.body}")
        raise
        return HttpResponseBadRequest(f"Expected POST to contain JSON formatted data, not: {request.body}")

    # Make sure the POST has all the expected fields:

    expected_fields = 'webhook_type', 'webhook_code', 'item_id'
    for field in expected_fields:
        if field not in post:
            return HttpResponseBadRequest(f"POST missing expected field: '{field}'")

    # Handle the different kinds of webhook.

    if post['webhook_type'] != 'TRANSACTIONS':
        return HttpResponseBadRequest(f"Expected a TRANSACTION webhook, not {post['webhook_type']}")

    if post['webhook_code'] in ('INITIAL_UPDATE', 'HISTORICAL_UPDATE'):
        # Ignore transactions that happened in the past.  Two Cents only cares 
        # about transactions made after budgeting has begun.
        return HttpResponse(f"Skipping {post['webhook_code']} for item_id={post['item_id']}")

    elif post['webhook_code'] == 'DEFAULT_UPDATE':
        bank = models.bank_from_webhook(post['item_id'])
        models.sync_transactions(bank)

    elif post['webhook_code'] == 'TRANSACTIONS_REMOVED':
        # Definitely need to handle this specially...
        raise NotImplementedError

    else:
        return HttpResponseBadRequest(f"Unknown type of TRANSACTION webhook: {post['webhook_code']}")


    return HttpResponse('')




