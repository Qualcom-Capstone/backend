from django.urls import path
from . import views

urlpatterns = [
    path('cars', views.create_car_data, name='create_car_data'),
    path('cars', views.get_car_data_list, name='get_car_data_list'),
    path('cars/checked', views.get_checked_car_data_list, name='get_checked_car_data_list'),
    path('cars/unchecked', views.get_unchecked_car_data_list, name='get_unchecked_car_data_list'),
    path('cars/<int:pk>', views.update_car_data, name='update_car_data'),
    path('cars/<int:pk>', views.delete_car_data, name='delete_car_data'),
]