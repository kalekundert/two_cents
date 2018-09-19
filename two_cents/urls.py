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

from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path, include

import two_cents.views

urlpatterns = [
    path('', two_cents.views.home, name='2c_home'),
    path('accounts/', two_cents.views.accounts, name='2c_accounts'),
    path('budgets/', two_cents.views.budgets, name='2c_budgets'),
    path('transactions/', two_cents.views.transactions, name='2c_transactions'),

    path('user/', include('django.contrib.auth.urls')),
    path('user/sign-up/', two_cents.views.sign_up, name='sign_up'),

    path('admin/', admin.site.urls),
    #path('api-auth/', include('rest_framework.urls')),
]
