from rest_framework import serializers
from .models import SpeedViolation, Vehicle

#REST Framework에서 데이터를 직렬화하거나 역직렬화하는 역할 (Python -> JSON, JSON -> Python)

class SpeedViolationSerializer(serializers.ModelSerializer):
    plate_number = serializers.CharField(write_only=True) #번호판을 기반으로

    class Meta:
        model = SpeedViolation
        fields = ['id', 'plate_number', 'speed', 'location', 'timestamp']

    #POST 요청 시 차량 번호판을 기반으로 Vehicle 객체를 생성하거나 조회한 후,
    #새 SpeedViolation 객체를 생성
    def create(self, validated_data):
        plate_number = validated_data.pop('plate_number')
        vehicle, _ = Vehicle.objects.get_or_create(plate_number=plate_number)
        return SpeedViolation.objects.create(vehicle=vehicle, **validated_data)