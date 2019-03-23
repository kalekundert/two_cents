#!/usr/bin/env python3

from django.apps import AppConfig

class TwoCentsConfig(AppConfig):
    name = 'two_cents'

    def ready(self):
        import two_cents.signals
