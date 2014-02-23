#!/usr/bin/env python3

import argparse, argcomplete
import budget, ui
from pprint import pprint

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers()

def command(*args):
    import inspect
    import functools

    def decorator(cls, parsers=()):
        cls.run = staticmethod(cls.run)

        def run_with_session(arguments):
            with budget.open_db() as session:
                cls.run(session, arguments)

        for parser in (cls.parser,) + parsers:
            parser.set_defaults(command=run_with_session)


    if len(args) == 1 and inspect.isclass(args[0]):
        return decorator(args[0])
    else:
        return functools.partial(decorator, parsers=args)


@command
class ShowAccounts:
    parser = subparsers.add_parser('show')
    
    def run(session, arguments):  # (no fold)
        receipts = budget.get_new_receipts(session)
        pprint(receipts)


@command
class AddBank:
    parser = subparsers.add_parser('add-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())
    parser.add_argument('--username', '-u')
    parser.add_argument('--password', '-p')

    def run(session, arguments):  # (no fold)
        if budget.bank_exists(session, arguments.bank):
            print("Bank '{}' already exists.".format(arguments.bank))
            return

        username, password = ui.get_bank_info(
                arguments.username, arguments.password)

        bank = budget.Bank(arguments.bank, username, password)
        session.add(bank)

@command
class ShowBanks:
    parser = subparsers.add_parser('show-banks')

    def run(session, arguments):  # (no fold)
        import datetime

        banks = budget.get_banks(session)

        if not banks:
            print("No banks to show.  Use 'budget add-bank' to add some.")
            return

        row = '{0:25}{1}'
        print(row.format('Bank', 'Last Update'))
        print(23*'=' + '  ' + 11*'=')

        for bank in banks:
            title = bank.title
            date = bank.last_update.strftime('%m/%d/%Y')
            print(row.format(title, date))

@command
class UpdateBanks:
    parser = subparsers.add_parser('update-banks')

    def run(session, arguments):  # (no fold)
        for bank in budget.get_banks(session):
            print("Connecting to {}...".format(bank.title))
            bank.update(session)

            # Assign value to accounts...

@command
class ConfigureBank:
    parser = subparsers.add_parser('configure-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())
    parser.add_argument('--username', '-u')
    parser.add_argument('--password', '-p')

    def run(session, arguments):  # (no fold)
        if not budget.bank_exists(session, arguments.bank):
            print("Bank '{0}' not found.  Create it using 'budget add-bank {0}'.".format(arguments.bank))
            return

        bank = budget.get_bank(session, arguments.bank)
        bank.username_command, bank.password_command = ui.get_bank_info(
                arguments.username, arguments.password)

        session.add(bank)

@command
class RemoveBank:
    parser = subparsers.add_parser('remove-bank')
    parser.add_argument('bank', choices=budget.get_known_bank_names())

    def run(session, arguments):  # (no fold)
        if not budget.bank_exists(session, arguments.bank):
            print("Bank '{0}' not found.".format(arguments.bank))
            return

        bank = budget.get_bank(session, arguments.bank)
        session.delete(bank)


if __name__ == '__main__':
    argcomplete.autocomplete(parser)
    arguments = parser.parse_args()
    arguments.command(arguments)

