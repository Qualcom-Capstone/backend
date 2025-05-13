# backend/crud/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # /api/v1/crud/cars/ 경로: 차량 목록 조회 (GET) 및 새로운 차량 생성 (POST)
    path('cars/', views.car_list_create_view, name='car_list_create'),

    # /api/v1/crud/cars/{id}/ 경로: 특정 차량 조회 (GET), 업데이트 (PUT, PATCH), 삭제 (DELETE)
    path('cars/<int:pk>/', views.car_detail_view, name='car_detail'),

    # /api/v1/crud/cars/checked/ 경로: is_checked=True 차량 목록 조회 (GET)
    path('cars/checked/', views.get_checked_car_data_list, name='get_checked_car_data_list'),

    # /api/v1/crud/cars/unchecked/ 경로: is_checked=False 차량 목록 조회 (GET)
    path('cars/unchecked/', views.get_unchecked_car_data_list, name='get_unchecked_car_data_list'),



]