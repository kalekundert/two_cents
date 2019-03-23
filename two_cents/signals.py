#!/usr/bin/env python3

from two_cents import models

from django.dispatch import receiver
from django.db.models.signals import post_save

@receiver(post_save, sender=models.User)
def on_init_user(sender, instance, created, **kwargs):
    if created:
        models.init_user(instance)

