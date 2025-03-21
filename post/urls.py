from backend.urls import path

from . import views
from .views import create_post

urlpatterns = [
    path("", views.index),
    path('posts/', create_post, name='create_post'),
]