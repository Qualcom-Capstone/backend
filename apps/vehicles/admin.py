from django.contrib import admin
from .models import Vehicle, DeviceToken


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['id', 'plate_number', 'owner_name', 'fcm_token_short', 'created_at']
    list_filter = ['created_at']
    search_fields = ['plate_number', 'owner_name', 'owner_phone']
    readonly_fields = ['created_at', 'updated_at']

    def fcm_token_short(self, obj):
        if obj.fcm_token:
            return f"{obj.fcm_token[:30]}..."
        return "-"
    fcm_token_short.short_description = 'FCM Token'


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ['id', 'token_short', 'registered_at']
    readonly_fields = ['registered_at']

    def token_short(self, obj):
        return f"{obj.token[:30]}..."
    token_short.short_description = 'Token'

