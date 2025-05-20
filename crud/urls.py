# backend/crud/urls.py
from django.urls import path
from .views import (
    CarListCreateView,
    CarRetrieveUpdateDeleteView,
    CarPartialUpdateView,
    CheckedCarDataListView,
    UncheckedCarDataListView,
    RegisterFCMTokenView,
)

urlpatterns = [
    path('cars', CarListCreateView.as_view(), name='car_list_create'),
    path('cars/<int:pk>', CarRetrieveUpdateDeleteView.as_view(), name='car_detail'),
    path('cars/<int:pk>/partial-update', CarPartialUpdateView.as_view(), name='car_partial_update'),

    path('cars/checked', CheckedCarDataListView.as_view(), name='car_checked_list'),
    path('cars/unchecked', UncheckedCarDataListView.as_view(), name='car_unchecked_list'),

    path('fcm/register', RegisterFCMTokenView.as_view(), name='register_fcm_token'),
]
