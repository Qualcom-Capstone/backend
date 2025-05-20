from rest_framework import serializers
from .models import CarData

from rest_framework import serializers
from .models import CarData

class CarDataSerializer(serializers.ModelSerializer):
    car_number = serializers.CharField(max_length=20, help_text="차량 고유 번호")
    car_speed = serializers.IntegerField(help_text="측정된 차량 속도 (km/h)")
    s3_key = serializers.CharField(max_length=512, help_text="S3에 저장된 객체의 키")  # ✅ 추가
    image_url = serializers.URLField(help_text="차량 이미지 URL")
    is_checked = serializers.BooleanField(default=False, help_text="확인 여부")

    class Meta:
        model = CarData
        fields = ['id', 'car_number', 'car_speed', 's3_key', 'image_url', 'is_checked', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
