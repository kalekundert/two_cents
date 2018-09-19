#!/usr/bin/env python3

import two_cents.wsgi
import two_cents.models as two_cents
from datetime import datetime

user = two_cents.User(
        username='test',
        password='test',
)
user.save()

account = two_cents.Account(
        title='Checking',
        order=1,
)
account.save()

account_user = two_cents.AccountUser(
        account=account,
        user=user,
        status='confirmed',
)
account_user.save()

account_plaid = two_cents.AccountPlaid(
        account=account,
        access_token='access-sandbox-c43c5ab3-5411-4c4a-8947-8214b9966e12',
        item_id='',
)
account_plaid.save()

budgets = [
        two_cents.Budget(
                title='Necessities',
                balance=234.56, # dollars
                allowance=250,  # dollars/mo
                last_update=datetime(2018,7,4),
                order=1,
        ),
        two_cents.Budget(
                title='Luxuries',
                balance=123.45, # dollars
                allowance=100,  # dollars/mo
                last_update=datetime(2018,7,4),
                order=2,
        ),
]
for budget in budgets:
    budget.save()



