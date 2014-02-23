#!/usr/bin/env python3

import readline
import budget
import re

def get_bank_info(username, password):
    if not username and not password:
        print("""\
Enter username and password commands.  You don't need to provide either 
command, but if you don't you'll have to provide the missing fields every time 
you download financial data from this bank.""")
        print()
        username = input("Username: ")
        password = input("Password: ")

    elif not username:
        print("""\
Enter a username command.  If no command is given, you'll be prompted for a 
username every time you download financial data from this bank.""")
        print()
        username = input("Username: ")

    elif not password:
        print("""\
Enter a password command.  If no command is given, you'll be prompted for a 
password every time you download financial data from this bank.""")
        print()
        password = input("Password: ")

    else:
        pass

    return username, password

def get_username(label):
    return input("Username for {}: ".format(label))

def get_password(label):
    import getpass
    return getpass.getpass("Password for {}: ".format(label))


def login_failed(error):
    try:
        print('Unable to login to {}.'.format(error.bank))
        print('User name: {}   Password: {}   (Ctrl-C to clear)'.\
                format(error.username, error.password)[:79], end='')
        input()

    finally:
        print('\r' + 79 * ' ')


############################

def download_debits(session):
    new_debits = []
    for bank in budget.get_banks(session):
        print("Connecting to {}...".format(bank.title))
        new_debits += bank.update(session)
    return new_debits

def assign_receipts(session, receipts):
    if not receipts:
        return
    elif len(receipts) == 1:
        print("Please assign the following debit to an account:")
    else:
        print("Please assign the following debits to accounts:")

    print()

    readline.parse_and_bind('tab: complete')
    readline.set_completer(AccountCompleter(session))

    for receipt in receipts:
        receipt.show(indent='  ')
        print()

        split_pattern = re.compile(r'(.*)=(\d*)')

        # Ask the user how this receipt should be assigned.  Several accounts 
        # may be specified, and each may be given a dollar value.  Those with 
        # values are referred to as explicit accounts, while those without are 
        # referred to as implicit.  The total value the explicit accounts may 
        # not exceed the value of the receipt.  Any value leftover after the 
        # explicit accounts are considered is divided evenly between the 
        # implicit accounts.  The most common case is that only one implicit 
        # account will be given.  In this case, the entire value of the receipt 
        # is charged to the that account.

        while True:
            implicit_accounts = []
            explicit_accounts = {}
            responses = input("Account: ")

            for response in responses.split():
                match = split_pattern.match(response)
                if match:
                    name, value = match.groups()
                    explicit_accounts[name] = int(100 * float(value))
                else:
                    implicit_accounts.append(response)

            all_accounts = explicit_accounts
            explicit_value = sum(explicit_accounts.values())

            if explicit_value > receipt.value:
                print("Too much money assigned.")
                continue

            if implicit_accounts:
                implicit_value = receipt.value - explicit_value
                value_chunk = implicit_value // len(implicit_accounts)

                if value_chunk == 0:
                    print("No money assigned to implicit accounts.")
                    continue

                for name in implicit_accounts:
                    all_accounts[name] = value_chunk
                    implicit_value -= value_chunk

                remainder_account = implicit_accounts[-1]
                all_accounts[remainder_account] += implicit_value

            if sum(all_accounts.values()) < receipt.value:
                print("Not enough money assigned.")
                continue

            break

        print()
        #print(all_accounts)
        receipt.assign(session, all_accounts)

def assign_savings(session):
    # Find out how much savings money if available.
    # Give the user a chance to allocate it.
    # Allow the user to not allocate all of it.

    for savings in budget.get_savings(session):
        pass

def show_accounts(session):
    for account in budget.get_accounts(session):
        account.update()
        print(account)


class AccountCompleter:

    def __init__(self, session):
        self.accounts = budget.get_accounts(session)
        self.account_names = [x.name for x in self.accounts]
        self.account_names.sort()

    def __call__(self, prefix, index):
        results = [x for x in self.account_names if x.startswith(prefix)]
        try: return results[index]
        except IndexError: return None


def yes_or_no(question, default=False):
    response = ''
    is_positive = lambda x: x.lower in ('y', 'yes')
    is_negative = lambda x: x.lower in ('n', 'no')
    is_valid = lambda x: is_positive(x) or is_negative(x)

    while not is_valid(response):
        response = input(question)
        if not response: return default

    if is_positive(response): return True
    if is_negative(response): return False

if __name__ == '__main__':
    with budget.open_db() as session:
        account = ''
        completer = AccountCompleter(session)
        readline.parse_and_bind('tab: complete')
        readline.set_completer(completer)

        while account != 'quit':
            account = input("Account: ")
            print(account.split())

