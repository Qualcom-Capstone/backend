from django.contrib import admin
from .models import Notification, NotificationLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'detection', 'title', 'status', 'retry_count', 'sent_at'
    ]
    list_filter = ['status', 'sent_at']
    search_fields = ['title', 'body', 'fcm_token']
    readonly_fields = ['created_at']
    raw_id_fields = ['detection']


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'car_data', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    raw_id_fields = ['car_data']

