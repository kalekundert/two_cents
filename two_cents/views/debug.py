#!/usr/bin/env python3

from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from pprint import pprint

@csrf_exempt
def ping(request):
    print('GET')
    pprint(request.GET)
    print()
    print('POST')
    pprint(request.POST)

    return HttpResponse('<html><body>Check terminal for request info</body></html>')
