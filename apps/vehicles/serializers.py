from rest_framework import serializers

from .models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "plate_number",
            "owner_name",
            "owner_phone",
            "fcm_token",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class VehicleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["plate_number", "owner_name", "owner_phone", "fcm_token"]


class FCMTokenUpdateSerializer(serializers.Serializer):
    fcm_token = serializers.CharField(max_length=255)
