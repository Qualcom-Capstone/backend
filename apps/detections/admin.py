from django.contrib import admin
from .models import Detection, CarData


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'ocr_result', 'detected_speed', 'speed_limit',
        'location', 'status', 'detected_at'
    ]
    list_filter = ['status', 'camera_id', 'detected_at']
    search_fields = ['ocr_result', 'location', 'camera_id']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['vehicle']


@admin.register(CarData)
class CarDataAdmin(admin.ModelAdmin):
    list_display = ['id', 'car_number', 'car_speed', 'is_checked', 'created_at']
    list_filter = ['is_checked', 'created_at']
    search_fields = ['car_number', 'gcs_key']
    readonly_fields = ['created_at', 'updated_at']

