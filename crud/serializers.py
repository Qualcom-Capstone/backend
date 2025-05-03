from rest_framework import serializers
from .models import CarData

class CarDataSerializer(serializers.ModelSerializer):

    car_number = serializers.CharField(max_length=20, help_text="차량 고유 번호")
    car_speed = serializers.IntegerField(help_text="측정된 차량 속도 (km/h)")
    image_url = serializers.URLField(help_text="차량 이미지 URL")
    is_checked = serializers.BooleanField(default=False, help_text="확인 여부")

    class Meta:
        model = CarData
        fields = ['id', 'car_number', 'car_speed', 'image_url', 'is_checked', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']  # 읽기 전용 필드 지정