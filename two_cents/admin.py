#!/usr/bin/env python3

from django.contrib import admin
from two_cents.models import registered_models

for model in registered_models:
    admin.site.register(model)
