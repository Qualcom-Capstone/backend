from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'detection_id', 'title', 'status', 'retry_count', 'sent_at'
    ]
    list_filter = ['status', 'sent_at']
    search_fields = ['title', 'body', 'fcm_token']
    readonly_fields = ['created_at']
