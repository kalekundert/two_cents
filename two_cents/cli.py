#!/usr/bin/env python3

"""\
Maintain a budget that updates every day.

Usage:
    two_cents [-d] [-D] [-I] [-h] [-v]
    two_cents add-bank <name> [-u <command>] [-p <command>]
    two_cents add-budget <name> [-b <dollars>] [-a <dollars-per-time>]
    two_cents describe-budgets [-e]
    two_cents download-payments [-I]
    two_cents reassign-payment <payment-id> <budget>
    two_cents set-allowance <budget> <allowance>
    two_cents show-allowance [<budgets>...]
    two_cents show-payments [<budget>]
    two_cents suggest-allowance [<budgets>...] [-s]
    two_cents transfer-allowance <dollars-per-time> <budget-from> <budget-to>
    two_cents transfer-money <dollars> <budget-from> <budget-to>

Options:
  -d, --download
        Force new transactions to be downloaded from the bank.  Downloading new 
        transactions is the default behavior, so the purpose of this flag is to 
        allow the --no-download flag to be overridden.

  -D, --no-download
        Don't download new transactions from the bank.  This can be a slow 
        step, so you may want to skip it if you know nothing new has happened.

  -I, --no-interaction
        Don't use stdin to prompt for passwords.  If a password command is 
        found in the database, use that.  Otherwise print an error message 
        and exit.

  -u, --username-cmd <command>
        When adding a new bank, use this option to specify a command that can 
        be used to get your username.  You will be prompted for one if this 
        option isn't specified.

  -p, --password-cmd <command>
        When adding a new bank, use this option to specify a command that can 
        be used to get your password.  You will be prompted for one if this 
        option isn't specified.

  -b, --initial-balance <dollars>
        When adding a new budget, specify how much money should start off in 
        the budget.

  -a, --initial-allowance <dollars-per-time>
        When adding a new budget, specify how quickly money should accumulate 
        in that budget.

  -s, --set-suggested-allowance
        Set the allowances for the relevant budgets to their suggested values 
        (based on past spending).

  -e, --edit
        Indicate that you want to create or update a description of your 
        budgeting scheme.

  -h, --help
        Print out this message.
        
  -v, --version
        Print the version number of the installed two_cents executable.
"""

import two_cents
import appdirs; dirs = appdirs.AppDirs('two_cents', 'username')
from contextlib import contextmanager

def main(argv=None, db_path=None):
    try:
        import docopt
        args = docopt.docopt(__doc__, argv)

        if args['--version']:
            print('two_cents 0.0')
            raise SystemExit

        if db_path is None:
            import os
            db_path = os.path.join(dirs.user_config_dir, 'budgets.db')

        with two_cents.open_db(db_path) as session:
            if args['add-bank']:
                add_bank(
                        session,
                        scraper_key=args['<name>'],
                        username_cmd=args['--username-cmd'],
                        password_cmd=args['--password-cmd'],
                )
            elif args['add-budget']:
                add_budget(
                        session,
                        name=args['<name>'],
                        initial_balance=args['--initial-balance'],
                        initial_allowance=args['--initial-allowance'],
                )
            elif args['describe-budgets']:
                describe_budgets(
                        edit=args['--edit'],
                )
            elif args['download-payments']:
                download_payments(
                        session,
                        interactive=not args['--no-interaction'],
                )
            elif args['reassign-payment']:
                reassign_payment(
                        session,
                        args['<payment-id>'],
                        args['<budget>'],
                )
            elif args['set-allowance']:
                set_allowance(
                        session,
                        args['<budget>'],
                        args['<allowance>'],
                )
            elif args['show-allowance']:
                show_allowance(
                        session,
                        args['<budgets>'],
                )
            elif args['show-payments']:
                show_payments(
                        session,
                        args['<budget>'],
                )
            elif args['suggest-allowance']:
                suggest_allowance(
                        session,
                        args['<budgets>'],
                        args['--set-suggested-allowance'],
                )
            elif args['transfer-money']:
                transfer_money(
                        session,
                        args['<dollars>'],
                        args['<budget-from>'],
                        args['<budget-to>'],
                )
            else:
                update_budgets(
                        session,
                        download=args['--download'] or not args['--no-download'],
                        interactive=not args['--no-interaction'],
                )
    except two_cents.UserError as error:
        print(error)
    except KeyboardInterrupt:
        print()

def add_bank(session, scraper_key, username_cmd=None, password_cmd=None):
    bank = two_cents.Bank(session, scraper_key)

    if not username_cmd and not password_cmd:
        print("""\
Enter username and password commands.  You don't need to provide either 
command, but if you don't you'll have to provide the missing fields every time 
you download financial data from this bank.""")
        print()
        username_cmd = prompt("Username: ")
        password_cmd = prompt("Password: ")

    elif not username_cmd:
        print("""\
Enter a username command.  If no command is given, you'll be prompted for a 
username every time you download financial data from this bank.""")
        print()
        username_cmd = prompt("Username: ")

    elif not password_cmd:
        print("""\
Enter a password command.  If no command is given, you'll be prompted for a 
password every time you download financial data from this bank.""")
        print()
        password_cmd = prompt("Password: ")

    bank.username_command = username_cmd
    bank.password_command = password_cmd

    session.add(bank)

def add_budget(session, name, initial_balance, initial_allowance):
    budget = two_cents.Budget(name, initial_balance, initial_allowance)
    session.add(budget)

def describe_budgets(edit=False):
    import os
    import subprocess

    description_path = os.path.join(dirs.user_config_dir, 'description.txt')

    if edit or not os.path.exists(description_path):
        editor = os.environ.get('EDITOR', 'vi')
        subprocess.call((editor, description_path))
    else:
        with open(description_path) as file:
            print(file.read().strip())

def download_payments(session, interactive=True):
    two_cents.download_payments(
            session,
            get_username_prompter(interactive),
            get_password_prompter(interactive),
    )

def reassign_payment(session, payment_id, budget):
    payment = two_cents.get_payment(session, payment_id)
    payment.assign(budget)

def set_allowance(session, budget, allowance):
    budget = two_cents.get_budget(session, budget)
    budget.allowance = two_cents.parse_allowance(allowance)

def show_allowance(session, budgets):
    with print_table('lr') as table:
        for budget in two_cents.get_budgets(session, *budgets):
            table.add_row([
                    budget.name.title(),
                    budget.pretty_allowance,
            ])

def show_payments(session, budget=None):
    for payment in two_cents.get_payments(session, budget):
        show_payment(payment)
        print()

def suggest_allowance(session, budgets, set=False):
    # Populate a table with suggested allowances for each budget, then display 
    # that table.

    with print_table('lr') as table:
        for budget in two_cents.get_budgets(session, *budgets):
            table.add_row([
                    budget.name.title(),
                    "{}/mo".format(two_cents.format_dollars(
                            two_cents.suggest_allowance(session, budget))),
            ])

    if set:
        for budget in two_cents.get_budgets(session, *budgets):
            budget.allowance = two_cents.suggest_allowance(session, budget)

def transfer_money(session, dollars, budget_from, budget_to):
    two_cents.transfer_money(
            two_cents.parse_dollars(dollars),
            two_cents.get_budget(session, budget_from),
            two_cents.get_budget(session, budget_to))

def update_budgets(session, download=True, interactive=True):
    if two_cents.get_num_budgets(session) == 0:
        raise two_cents.UserError("No budgets to display.  Use 'two_cents add-budget' to create some.")

    if download:
        print("Downloading recent transactions...")
        download_payments(session, interactive)

    assign_payments(session)
    two_cents.update_allowances(session)
    show_budgets(session)


def print(*args, **kwargs):
    import builtins
    return builtins.print(*args, **kwargs)

def prompt(message, password=False):
    if password:
        import getpass
        return getpass.getpass(message)
    else:
        return input(message)

def assign_payments(session):
    import readline

    # Handle the payments using a simple state machine.  This architecture 
    # facilitates commands like 'skip all' and 'ignore all'.

    class ReadEvalPrintLoop:

        def __init__(self):
            self.handle = self.default_handler

        def go(self, session):
            payments = two_cents.get_unassigned_payments(session)

            if not payments:
                return

            elif len(payments) == 1:
                print("Please assign the following payment to an budget:")
                print()

            else:
                print("Please assign the following payments to budgets:")
                print()

            for payment in payments:
                self.handle(payment)

        def default_handler(self, payment):
            show_payment(payment, indent='  ')
            print()

            while True:
                
                # Prompt the user for an assignment.

                command = prompt("Account: ")

                # See if the user wants to skip assigning one or more payments 
                # and come back to them later.

                if not command or command == 'skip':
                    break

                if command == 'skip all':
                    self.handle = self.null_handler
                    break

                # See if the user wants to ignore one or more payments.  These 
                # payments will be permanently excluded from the budget.

                if command == 'ignore':
                    payment.ignore()
                    break

                if command == 'ignore all':
                    payment.ignore()
                    self.handle = self.ignore_handler
                    break

                # Attempt to assign the payment to the specified budgets.  If 
                # the input can't be parsed, print an error and ask again.

                try:
                    payment.assign(command)
                    break

                except two_cents.UserError as error:
                    print(error.message)

            print()

        def ignore_handler(self, payment):
            payment.ignore()

        def null_handler(self, payment):
            pass

    class TabCompleter:

        def __init__(self, session):
            self.budgets = two_cents.get_budgets(session)
            self.commands = [x.name for x in self.budgets]
            self.commands += ['skip', 'ignore', 'all']
            self.commands.sort()

        def __call__(self, prefix, index):
            results = [x for x in self.commands if x.startswith(prefix)]
            try: return results[index]
            except IndexError: return None


    readline.parse_and_bind('tab: complete')
    readline.set_completer(TabCompleter(session))

    loop = ReadEvalPrintLoop()
    loop.go(session)

def show_budgets(session):
    """
    Print a line briefly summarizing each budget.
    """
    
    # I had to hack table.right_padding_width a little to format the recovery 
    # time the way I wanted.  Basically, I use table.right_padding_width to add 
    # manual padding, then I remove the padding once the table is complete.

    with print_table('lr') as table:
        for budget in two_cents.get_budgets(session):
            table.add_row([
                budget.name.title() + ' ' * table.right_padding_width,
                budget.pretty_balance + ' ',
                '' if budget.recovery_time <= 0 else 
                    '({} {})'.format(budget.recovery_time,
                        'day' if budget.recovery_time == 1 else 'days')
            ])
        table.right_padding_width = 0

@contextmanager
def print_table(alignments=None):
    import prettytable

    table = prettytable.PrettyTable()
    table.set_style(prettytable.PLAIN_COLUMNS)
    table.header = False

    yield table

    if alignments is not None:
        for column, alignment in zip(table.field_names, alignments):
            table.align[column] = alignment

    print(table)

def show_payment(payment, indent=''):
    import textwrap

    print("{}Id: {}".format(indent, payment.id))
    print("{}Bank: {}".format(indent, payment.bank.title))
    print("{}Date: {}".format(indent, two_cents.format_date(payment.date)))
    print("{}Value: {}".format(indent, two_cents.format_dollars(payment.value)))

    if payment.assignment is not None:
        print("{}Assignment: {}".format(indent, payment.assignment))

    if len(payment.description) < (79 - len(indent) - 13):
        print("{}Description: {}".format(indent, payment.description))
    else:
        description = textwrap.wrap(
                payment.description, width=79,
                initial_indent=indent+'  ', subsequent_indent=indent+'  ')

        print("{}Description:".format(indent))
        print('\n'.join(description))

def get_username_prompter(interactive=True):
    def username_prompter(bank, error_message):
        if error_message: print(error_message)
        if not interactive: raise SystemExit
        return prompt("Username for {}: ".format(bank))
    return username_prompter

def get_password_prompter(interactive=True):
    def password_prompter(bank, error_message):
        if error_message: print(error_message)
        if not interactive: raise SystemExit
        return prompt("Password for {}: ".format(bank), password=True)
    return password_prompter

