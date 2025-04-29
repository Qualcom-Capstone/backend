from rest_framework import serializers
from .models import CarData

class CarDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarData
        fields = ['id', 'car_number', 'car_speed', 'image_url', 'is_checked', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']  # 읽기 전용 필드 지정