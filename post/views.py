from django.shortcuts import render
from django.http import HttpResponse


def index(request):
    return HttpResponse("설정이 완료되었습니다.")
# Create your views here.
