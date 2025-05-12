from backend.urls import path

from . import views
import cv2

cv2.imread('adf')

urlpatterns = [
    path("", views.index),
]