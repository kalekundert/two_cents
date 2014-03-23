#!/usr/bin/env python3

import sys, argparse, argcomplete, readline
import budget, banking
from pprint import pprint

# Things to do
# ============
# 1. Implement remaining commands
# 2. Write tests for all untested commands.
# 3. Add allowances to 'show-accounts'

parser = argparse.ArgumentParser()
parser.add_argument('--database', default='~/.config/budget/budget.db')
subparsers = parser.add_subparsers()

def command(*args):
    import inspect
    import functools
    import types

    def decorator(cls, parsers=()):
        error = TypeError("Command classes must define a static run method().")
        if not hasattr(cls, 'run'): raise error
        if not isinstance(cls.run, types.FunctionType): raise error

        def run_with_session(arguments):
            with budget.open_db(arguments.database) as session:
                cls.run(session, arguments)

        for parser in (cls.parser,) + parsers:
            parser.set_defaults(command=run_with_session)


    if len(args) == 1 and inspect.isclass(args[0]):
        return decorator(args[0])
    else:
        return functools.partial(decorator, parsers=args)

def setup_allowance_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--allowance', '-a', nargs=2)
    group.add_argument('--savings', '-s', action='store_true')


@command
class AddAccount:
    parser = subparsers.add_parser('add')
    parser.add_argument('name')
    setup_allowance_arguments(parser)
    
    @staticmethod   # (no fold)
    def run(session, arguments):
        require_no_account(session, arguments.name)
        account = budget.Account(arguments.name)
        session.add(account)
        setup_allowance(session, account, arguments)

@command
class AddBank:
    parser = subparsers.add_parser('add-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())
    parser.add_argument('--username', '-u')
    parser.add_argument('--password', '-p')

    @staticmethod   # (no fold)
    def run(session, arguments):
        if budget.bank_exists(session, arguments.bank):
            print("Bank '{}' already exists.".format(arguments.bank))
            return

        username, password = get_bank_info(
                arguments.username, arguments.password)

        bank = budget.Bank(arguments.bank, username, password)
        session.add(bank)

class AddSavings:
    pass

class MakeTransfer:
    pass

@command
class ModifyAllowance:
    parser = subparsers.add_parser('modify-allowance')
    parser.add_argument('name')
    setup_allowance_arguments(parser)

    @staticmethod   # (no fold)
    def run(session, arguments):
        account = require_account(arguments.name)
        setup_allowance(session, account, arguments)

@command
class ModifyBank:
    parser = subparsers.add_parser('modify-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())
    parser.add_argument('--username', '-u')
    parser.add_argument('--password', '-p')

    @staticmethod   # (no fold)
    def run(session, arguments):
        if not budget.bank_exists(session, arguments.bank):
            print("Bank '{0}' not found.  Create it using 'budget add-bank {0}'.".format(arguments.bank))
            return

        bank = budget.get_bank(session, arguments.bank)
        bank.username_command, bank.password_command = get_bank_info(
                arguments.username, arguments.password)

        session.add(bank)

class ModifySavings:
    pass

@command
class RemoveAccount:
    parser = subparsers.add_parser('config')
    parser.add_argument('account')

    @staticmethod   # (no fold)
    def run(session, arguments):
        account = require_ccount(session, arguments.account)
        session.delete(account)

@command
class RemoveBank:
    parser = subparsers.add_parser('remove-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())

    @staticmethod   # (no fold)
    def run(session, arguments):
        try:
            bank = budget.get_bank(session, arguments.bank)
            session.delete(bank)
        except budget.NoSuchBank:
            print("Bank '{0}' not found.".format(arguments.bank))

@command
class RenameAccount:
    parser = subparsers.add_parser('rename')
    parser.add_argument('old-name')
    parser.add_argument('new-name')
    setup_allowance_arguments(parser)

    @staticmethod   # (no fold)
    def run(session, arguments):
        require_no_account(session, arguments.new_name)
        account = require_account(session, arguments.old_name)
        account.name = arguments.new_name
        session.add(account)

@command
class ShowAccounts:
    parser = subparsers.add_parser('show')
    parser.add_argument('--fast', action='store_true')
    
    @staticmethod   # (no fold)
    def run(session, arguments):
        require_any_accounts(session)
        require_any_banks(session)

        update_accounts(session)
        if not arguments.fast: update_banks(session)
        assign_receipts(session)
        assign_savings(session)

        for account in budget.get_accounts(session):
            account.show()

@command
class ShowBanks:
    parser = subparsers.add_parser('show-banks')

    @staticmethod   # (no fold)
    def run(session, arguments):
        import datetime

        require_any_banks(session)
        banks = budget.get_banks(session)

        row = '{0:25}{1}'
        print(row.format('Bank', 'Last Update'))
        print(23*'=' + '  ' + 11*'=')

        for bank in banks:
            title = bank.title
            date = bank.last_update.strftime('%m/%d/%Y')
            print(row.format(title, date))

@command
class UpdateAccounts:
    parser = subparsers.add_parser('update')

    @staticmethod   # (no fold)
    def run(session, arguments):
        require_any_accounts(session)
        update_accounts(session)

@command
class UpdateBanks:
    parser = subparsers.add_parser('update-banks')

    @staticmethod   # (no fold)
    def run(session, arguments):
        require_any_banks(session)
        update_banks(session)


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

def get_bank_username(bank):
    try: return bank.username
    except budget.AskForUsername:
        return input("Username for {}: ".format(bank.title))

def get_bank_password(bank):
    try: return bank.password
    except budget.AskForPassword:
        import getpass
        return getpass.getpass("Password for {}: ".format(bank.title))

def require_account(session, name):
    try: return budget.get_account(session, name)
    except budget.NoSuchAccount:
        print("Account '{}' not found.".format(name))
        sys.exit()

def require_no_account(session, name):
    if budget.account_exists(session, name):
        print("Account '{}' already exists.".format(name))
        sys.exit()

def require_any_accounts(session):
    if budget.get_num_accounts(session) == 0:
        print("No accounts found.  Add an account using 'budget add'.")
        sys.exit()

def require_any_banks(session):
    if budget.get_num_banks(session) == 0:
        print("No banks found.  Add a bank using 'budget add-bank'.")
        sys.exit()

def update_accounts(session):
    budget.update_accounts(session)

def update_banks(session):
    for bank in budget.get_banks(session):
        try:
            print("Connecting to {}...".format(bank.title))
            username = get_bank_username(bank)
            password = get_bank_password(bank)
            bank.update(session, username, password)

        except banking.LoginError as error:
            try:
                print('Unable to login to {}.'.format(bank.title))
                print('User name: {}   Password: {}   (Ctrl-C to clear)'.\
                        format(username, password)[:79], end='')
                input()

            except (KeyboardInterrupt, EOFError):
                print('\r' + 79 * ' ')

def setup_allowance(session, account, arguments):
    if arguments.savings:
        return

    try:
        # Ask the user to specify a new allowance

        header = "Please provide an allowance for this account."
        prompt = "Allowance: "

        if arguments.allowance is None: input = None
        else: input = str.join(' ', arguments.allowance)

        value, frequency = setup_budget(header, prompt, input)

        # Cancel all of the existing allowances for this account.

        for allowance in account.allowances:
            allowance.cancel(session)

        # Create the allowance specified by the user.

        allowance = budget.Allowance(account, value, frequency)
        session.add(allowance)

    except DontMakeBudget:
        pass

def setup_savings(arguments):
    header = "Please provide a savings budget:"
    prompt = "Budget: "

    try:
        value, frequency = setup_budget(header, prompt, arguments.budget)
        savings = Savings(value, frequency)
        session.add(savings)

    except DontMakeBudget:
        pass

def setup_budget(header, prompt, initial_input=None):

    class TabCompleter:

        def __call__(self, prefix, index):
            frequencies = 'daily', 'monthly', 'yearly'
            results = [x for x in frequencies if x.startswith(prefix)]
            try: return results[index]
            except IndexError: return None


    readline.parse_and_bind('tab: complete')
    readline.set_completer(TabCompleter())

    first_iteration = True
    first_prompt = True

    while True:

        # Ask the user for a budget.

        if first_iteration and initial_input is not None:
            command = initial_input
        else:
            if first_prompt: print(header)
            command = input(prompt); first_prompt = False

        first_iteration = False

        # If no input is given, don't create a budget.

        if not command:
            raise DontMakeBudget

        # Make sure the requested budget is legal.

        try:
            return budget.parse_budget(command)
        except ValueError:
            message = "Input '{}' not understood.  "
            message += "Expecting: '<value> <frequency>'"
            print(message.format(command))

def assign_receipts(session):
    receipts = budget.get_new_receipts(session)
    
    if not receipts:
        return
    elif len(receipts) == 1:
        print("Please assign the following transaction to an account:")
        print()
    else:
        print("Please assign the following transactions to accounts:")
        print()

    # Handle the receipts using a simple state machine.  This architecture 
    # facilitates commands like 'skip all' and 'ignore all'.

    class ReadEvalPrintLoop:

        def __init__(self):
            self.handle = self.default_handler

        def default_handler(self, receipt):
            receipt.show(indent='  ')
            print()

            try:
                accounts = assign_to_accounts(session, receipt.value)
                receipt.assign(session, accounts)

            except IgnoreTransaction:
                receipt.ignore(session)

            except IgnoreAllTransactions:
                self.handle = self.ignore_handler
                self.handle(receipt)

            except SkipTransaction:
                pass

            except SkipAllTransactions:
                self.handle = self.null_handler

        def ignore_handler(self, receipt):
            receipt.ignore(session)

        def null_handler(self, receipt):
            pass


    loop = ReadEvalPrintLoop()
    for receipt in receipts:
        loop.handle(receipt)

def assign_savings(session):
    print("Savings not yet supported.")

def assign_to_accounts(session, value):
    import re
    import math

    class TabCompleter:

        def __init__(self, session):
            self.accounts = budget.get_accounts(session)
            self.commands = [x.name for x in self.accounts]
            self.commands += ['skip', 'ignore', 'all']
            self.commands.sort()

        def __call__(self, prefix, index):
            results = [x for x in self.commands if x.startswith(prefix)]
            try: return results[index]
            except IndexError: return None


    readline.parse_and_bind('tab: complete')
    readline.set_completer(TabCompleter(session))

    split_pattern = re.compile(r'(.*)=(\d*)')
    raw_value = value
    total_value = abs(value)

    # Ask the user how the given value should be assigned.  Several accounts 
    # may be specified, and each may be given a dollar value.  Those with 
    # values are referred to as explicit accounts, while those without are 
    # referred to as implicit.  The total value the explicit accounts may not 
    # exceed the value of the receipt.  Any value leftover after the explicit 
    # accounts are considered is divided evenly between the implicit accounts.  
    # The most common case is that only one implicit account will be given.  In 
    # this case, the entire value of the receipt is charged to the that 
    # account.

    while True:
        implicit_accounts = []
        explicit_accounts = {}

        # Parse the command entered by the user.

        command = input("Account: ")

        for token in command.split():
            match = split_pattern.match(token)
            if match:
                token_name, token_value = match.groups()
                token_value = budget.to_cents(token_value)
                explicit_accounts[token_name] = abs(token_value)
            else:
                implicit_accounts.append(token)

        processed_accounts = explicit_accounts
        explicit_value = sum(explicit_accounts.values())

        # Skip this account if no command was given.

        if not command or command == 'skip':
            raise SkipTransaction

        if command == 'skip all':
            raise SkipAllTransactions

        # Treat the ignore command specially.  If ignoring is enabled, handle 
        # the ignore command by raising an exception as a signal to the calling 
        # code.  Otherwise, treat the ignore command like a skip command.

        if command == 'ignore':
            raise IgnoreTransaction

        if command == 'ignore all':
            raise IgnoreAllTransactions

        # Make sure any accounts referenced actually exist.

        account_names = list(explicit_accounts.keys()) + implicit_accounts
        unknown_accounts = budget.get_unknown_accounts(session, account_names)

        if unknown_accounts:
            print("Unknown account '{}'.".format(unknown_accounts[0]))

        # Complain if too much money has been allocated.

        if explicit_value > total_value:
            print("Too much money assigned.")
            continue

        # Determine how much money should be assigned to the implicit accounts.

        if implicit_accounts:
            implicit_value = total_value - explicit_value
            value_chunk = implicit_value // len(implicit_accounts)

            if value_chunk == 0:
                print("No money assigned to implicit accounts.")
                continue

            for name in implicit_accounts:
                processed_accounts[name] = value_chunk
                implicit_value -= value_chunk

            remainder_account = implicit_accounts[-1]
            processed_accounts[remainder_account] += implicit_value

        # Complain if too little money has been allocated.  This can only 
        # happen if no implicit account were given.

        if sum(processed_accounts.values()) < total_value:
            print("Not enough money assigned.")
            assert not implicit_accounts
            continue

        # Reapply the correct signs to the results.  Before this point, every 
        # value was made positive to simplify the algorithm.

        fix_sign = lambda x: int(math.copysign(x, raw_value))

        for account, value in processed_accounts.items():
            processed_accounts[account] = fix_sign(value)

        # Return a dictionary which tells how much of the original value is 
        # assigned to each account.

        return processed_accounts


class SkipTransaction (Exception):
    pass

class SkipAllTransactions (Exception):
    pass

class IgnoreTransaction (SkipTransaction):
    pass

class IgnoreAllTransactions (SkipAllTransactions):
    pass

class DontMakeBudget (Exception):
    pass


def main():
    argcomplete.autocomplete(parser)
    arguments = parser.parse_args()
    arguments.command(arguments)

if __name__ == '__main__':
    main()

