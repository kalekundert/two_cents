#!/usr/bin/env python3

import argh
import budget
import ui

def show(*names):
    with budget.open_db() as session:

        # Download new debits from all the banks.

        debits = ui.download_debits(session)
        
        # Assign each new debit to an account.

        ui.assign_debits(session, debits)

        # Decide how to allocate any new savings credits.

        #ui.assign_savings(session)

        # Update and show all accounts.

        #ui.show_accounts(session)


def add_bank(name):
    with budget.open_db() as session:
        bank = budget.Bank(name)
        session.add(bank)

        # option to set last_update date. default=today

def add_filter():
    pass

def add_account(name):
    with budget.open_db() as session:
        account = budget.Account(name)
        session.add(account)

        # Ask about creating a budget...

def remove_account(name):
    with budget.open_db() as session:
        account = budget.get_account(session, name)
        session.delete(account)

argh.dispatch_commands([
    show,
    add_bank,
    add_account,
    remove_account,
])

