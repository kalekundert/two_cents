"""two_cents URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import two_cents.views

from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, include

urlpatterns = [
    path('', two_cents.views.home.show, name='2c_home'),

    path('banks/add/', two_cents.views.banks.add, name='2c_banks_add'),
    path('banks/sync/', two_cents.views.banks.sync, name='2c_banks_sync'),

    path('accounts/', two_cents.views.accounts.show, name='2c_accounts'),
    path('accounts/toggle', two_cents.views.accounts.toggle, name='2c_accounts_toggle'),

    path('budgets/', two_cents.views.budgets.show, name='2c_budgets'),
    path('budgets/add', two_cents.views.budgets.add, name='2c_budgets_add'),

    path('transactions/', two_cents.views.transactions.show, name='2c_transactions'),

    path('users/', include('django.contrib.auth.urls')),
    path('users/sign-up/', two_cents.views.users.sign_up, name='sign_up'),

    path('admin/', admin.site.urls),
    path('ping/', two_cents.views.debug.ping)
]
