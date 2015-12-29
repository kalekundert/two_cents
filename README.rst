Two Cents
=========
Two Cents is a continuously (rather than monthly) updating budget program.  So 
instead of saying "You have $500 to spend on groceries in April", Two Cents 
either says "You are over your grocery budget right now, try not to spend more 
than you have to" or "You are within your grocery budget, go ahead and make a 
nice dinner".  In this way Two Cents directly tells you whether or not it's OK 
to splurge at the moment, which is a critical 

Each budget can have an allowance, which would be something like ``$500/mo''.  
Every time you run ``two_cents``, it will calculate how many seconds have 
elapsed since you called it and apply allowances for each budget accordingly.  
It will also download recent activity from your bank, ask you to assign 
transactions to budgets, and credit or debit your budgets accordingly.  
Finally, it will display the balance for each budget.  For budgets with 
negative balances, it will also display an estimate for how long it will take 
for the budget to return to the black.

Installation
------------
Two Cents is available on PyPI, so you can install it with ``pip''::

   pip install two_cents

