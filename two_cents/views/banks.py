#!/usr/bin/env python3

"""
Views for managing bank information.  These views are only relevant to users 
who are using Plaid to automatically monitor transaction information.
"""

import json

from two_cents import models
from two_cents.utils import *

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils import timezone

@login_required
@require_POST
def add(request):
    """
    This method is triggered when a user successfully completes the Plaid Link 
    form.
    """

    # An example of the data that will be posted to us by Plaid Link:
    # {'account': {'id': None',
    #              'mask': None',
    #              'name': None',
    #              'subtype': None',
    #              'type': None'},
    #  'account_id': None,
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

    info('Adding a bank')
    post = json.loads(request.body)
    pprint(post)

    plaid_client = models.get_plaid_client()
    exchange = plaid_client.Item.public_token.exchange(post['public_token'])

    # Check to see if the credential already exists.  If so, maybe the user is 
    # changing which accounts they want to use?  Maybe I shouldn't select 
    # accounts at this point, and just provide a way to ignore certain accounts 
    # after the fact...

    credential = models.PlaidCredential.objects.create(
            user=request.user,
            title=post['institution']['name'],
            last_update=timezone.now(),
            ui_order=request.user.plaid_credential_set.count(),
            plaid_item_id=exchange['item_id'],
            plaid_access_token=exchange['access_token'],
    )
    
    # Download more complete account information (i.e. including account 
    # balances) for each of the new accounts.

    # {
    #   "accounts": [{
    #      "account_id": "QKKzevvp33HxPWpoqn6rI13BxW4awNSjnw4xv",
    #      "balances": {
    #        "available": 100,
    #        "current": 110,
    #        "limit": null,
    #        "iso_currency_code": "USD",
    #        "unofficial_currency_code": null
    #      },
    #      "mask": "0000",
    #      "name": "Plaid Checking",
    #      "official_name": "Plaid Gold Checking",
    #      "subtype": "checking",
    #      "type": "depository"
    #   }],
    #   "item": {object},
    #   "request_id": "m8MDnv9okwxFNBV"
    # }

    accounts = plaid_client.Accounts.balance.get(exchange['access_token'])

    for i, fields in enumerate(accounts['accounts']):
        account = models.PlaidAccount.objects.create(
                remote_id=fields['account_id'],
                title=fields['name'],
                balance=fields['balances']['current'],
                last_digits=fields['mask'],
                ignore=False,
                ui_order=i,
        )
        models.PlaidAccountCredential.objects.create(
                credential=credential,
                account=account,
        )

    return redirect('2c_home')

@require_POST
@csrf_exempt
def sync(request):
    """
    Plaid will POST to this URL when it downloads new transaction data for an 
    account.  (The webhook is configured by Plaid Link when the user first 
    links to their bank.)
    
    Note that the request just contains the `item_id` of the account in 
    question.  It doesn't contain any transaction data, or even any 
    authenticating information.  So we need to react to the request by querying 
    Plaid for the actual data and updating our model.
    """

    # This should probably return JSON, and be part of the API.

    # Make sure the POST has all the expected fields:

    try:
        post = json.loads(request.body)
    except:
        return HttpResponseBadRequest(f"Expected POST to contain JSON formatted data, not: {request.body}")

    expected_fields = 'webhook_type', 'webhook_code', 'item_id'
    for field in expected_fields:
        if field not in post:
            return HttpResponseBadRequest(f"POST missing expected field: '{field}'")

    # Handle the different kinds of webhook.

    if post['webhook_type'] != 'TRANSACTIONS':
        return HttpResponseBadRequest(f"Expected a TRANSACTION webhook, not {post['webhook_type']}")

    elif post['webhook_code'] in ('INITIAL_UPDATE', 'HISTORICAL_UPDATE'):
        # Ignore transactions that happened in the past.  Two Cents only cares 
        # about transactions made after budgeting has begun.
        return HttpResponse(f"Skipping {post['webhook_code']} for item_id={post['item_id']}")

    elif post['webhook_code'] == 'DEFAULT_UPDATE':
        credential = models.get_plaid_credential_from_webhook(post['item_id'])
        models.sync_transactions(credential)
        return HttpResponse("Transactions updated.")

    elif post['webhook_code'] == 'TRANSACTIONS_REMOVED':
        # Definitely need to handle this specially...
        raise NotImplementedError

    else:
        return HttpResponseBadRequest(f"Unknown type of TRANSACTION webhook: {post['webhook_code']}")

    raise AssertionError




