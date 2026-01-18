from rest_framework import serializers
from .models import Vehicle, DeviceToken


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            'id', 'plate_number', 'owner_name', 'owner_phone',
            'fcm_token', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class VehicleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['plate_number', 'owner_name', 'owner_phone', 'fcm_token']


class FCMTokenUpdateSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(max_length=255)


class DeviceTokenSerializer(serializers.ModelSerializer):
    """레거시 호환용"""
    class Meta:
        model = DeviceToken
        fields = ['id', 'token', 'registered_at']
        read_only_fields = ['id', 'registered_at']

