from django.contrib import admin

from .models import Detection


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "ocr_result",
        "detected_speed",
        "speed_limit",
        "location",
        "status",
        "vehicle_id",
        "detected_at",
    ]
    list_filter = ["status", "camera_id", "detected_at"]
    search_fields = ["ocr_result", "location", "camera_id"]
    readonly_fields = ["created_at", "updated_at"]
