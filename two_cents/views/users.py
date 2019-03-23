#!/usr/bin/env python3

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm

def sign_up(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(
                    username=form.cleaned_data.get('username'),
                    password=form.cleaned_data.get('password1'),
            )
            login(request, user)
            return redirect('2c_home')
    else:
        form = UserCreationForm()

    return render(request, 'registration/sign_up.html', {'form': form})

