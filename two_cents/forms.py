#!/usr/bin/env python3

from two_cents import models
from django.forms import ModelChoiceField
from django.forms.widgets import HiddenInput

class FamilyChoiceField(ModelChoiceField):
    """
    Allow the user to select one of their families.

    If the user only has their personal family, no choice is presented and that 
    family is returned to the backend as a hidden form element.  If the user 
    does have families to choose between, those families are presented as a 
    dropdown box.

    Note that this field requires that the user object be given as an argument 
    to the constructor.  This more or less requires that the whole form (or 
    formset) be assembled directly in the view, rather than at module scope.
    """

    def __init__(self, user):
        self.user = user

    def __call__(self, **kwargs):
        super().__init__(
                initial=models.get_default_family(self.user),
                **kwargs
        )

        if len(kwargs['queryset']) == 1:
            self.widget = HiddenInput()

        return self

    def label_from_instance(self, family):
        return family.get_title(self.user)


