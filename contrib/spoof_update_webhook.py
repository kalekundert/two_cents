#!/usr/bin/env python3

"""\
Trigger the development server to query Plaid for new transactions.

Usage:
    spoof_update_webhook.py [<host>] [<kind>]

Arguments:
    <host>
        Where to send the update request.  By default, the request is sent to 
        the local development server.
    
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
host = args['<host>'] or 'http://127.0.0.1:8000'
kind = args['<kind>'] or 'default'

# Get an 'item_id' from the first bank in the database.
#credential = two_cents.PlaidCredential.objects.all()[0]
#item_id = credential.plaid_item_id
#print(credential)
item_id = 'mYdOzBk0DNTEqVYkdVdJCQAm90ZQrQSM1xPv8'

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

print("Request:")
pprint(queries[kind])

response = requests.post(f'{host}/banks/sync/', json=queries[kind])

print("Response:")
print(response.text)

