#!/usr/bin/env python3

"""\
Trigger the development server to query Plaid for new transactions.

Usage:
    spoof_update_webhook.py [<kind>]

Arguments:
    <kind>
        The kind of transaction update to spoof.  Options are:
        - "default": An update as a result of routine polling.
        - "initial": The first update after creating an account.
        - "historical": When the complete transaction history of a new account 
          has been downloaded. 
        - "removed": When a transaction has been removed.
"""

import docopt
import requests
import two_cents.wsgi
import two_cents.models as two_cents

# CSRF is going to be a problem.  I think I might need to either add plaid as a 
# trusted host, or exempt the URL responsible for handling the plaid webhook.  
# I think the latter is reasonable, since the POST is basically safe: it just 
# instructs the server to go look up information for itself; it doesn't 
# directly control anything about the server itself.  And it's not on the 
# behalf of any user.

args = docopt.docopt(__doc__)
kind = args['<kind>'] or 'default'

# Get an 'item_id' from the first bank in the database.
bank = two_cents.Bank.objects.all()[0]
item_id = bank.plaid_item_id
print(bank)

# Prepare queries:
queries = {
        # Error checking:
        'empty': {},
        'bad-type': {
            'webhook_type': 'BAD_TYPE',
            'webhook_code': '...',
            'item_id': item_id,
        },
        'bad-code': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'BAD_CODE',
            'item_id': item_id,
        },
        'no-item': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'INITIAL_UPDATE',
        },

        # Initial Transaction Webhook
        'initial': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'INITIAL_UPDATE',
            'item_id': item_id,
            'error': None,
            'new_transactions': 19,
        },

        # Historical Transaction Webhook
        'historical': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'HISTORICAL_UPDATE',
            'item_id': item_id,
            'error': None,
            'new_transactions': 231
        },

        # Default Transaction Webhook
        'default': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'DEFAULT_UPDATE',
            'item_id': item_id,
            'error': None,
            'new_transactions': 3
        },

        # Removed Transaction Webhook
        'removed': {
            'webhook_type': 'TRANSACTIONS',
            'webhook_code': 'TRANSACTIONS_REMOVED',
            'item_id': item_id,
            'removed_transactions': [
                'yBVBEwrPyJs8GvR77N7QTxnGg6wG74H7dEDN6',
                'kgygNvAVPzSX9KkddNdWHaVGRVex1MHm3k9no'
            ],
            'error': None
        },
}

# Transaction notifications are posted as JSON to your webhook, and they might 
# appear in a few different forms:
response = requests.post('http://127.0.0.1:8000/accounts/sync/', json=queries[kind])
print(response.text)

