"""\
Usage:
    two_cents_daemon
"""

from .settings import DATABASES
from django.conf import settings

settings.configure(DATABASES=DATABASES)

def download_transactions():
    pass

def update_budgets():
    pass
    
def main():
    import docopt
    docopt.docopt(__doc__)
