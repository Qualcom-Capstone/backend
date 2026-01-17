# serializers.py
from rest_framework import serializers
from .models import CarData


class CarDataSerializer(serializers.ModelSerializer):
    car_number = serializers.CharField(
        max_length=20,
        help_text="차량 고유 번호 (OCR로 추출되거나, 실패 시 비어있을 수 있음)",
        required=False,  # OCR로 채워지므로 POST 요청 시 필수가 아님
        allow_blank=True,
        allow_null=True
    )
    car_speed = serializers.IntegerField(help_text="측정된 차량 속도 (km/h)")  #
    s3_key = serializers.CharField(max_length=512, help_text="GCS에 저장된 객체의 키 (blob name)")  # 필드명은 호환성 유지
    image_url = serializers.URLField(help_text="차량 이미지 URL")  #
    is_checked = serializers.BooleanField(default=False, help_text="확인 여부")  #

    # POST 요청 시 추가로 받을 x, y, w, h 좌표
    x = serializers.FloatField(help_text="관심영역(ROI)의 상대 x 좌표 (0.0 ~ 1.0)", required=True)
    y = serializers.FloatField(help_text="관심영역(ROI)의 상대 y 좌표 (0.0 ~ 1.0)", required=True)
    w = serializers.FloatField(help_text="관심영역(ROI)의 상대 너비 (0.0 초과 ~ 1.0)", required=True)
    h = serializers.FloatField(help_text="관심영역(ROI)의 상대 높이 (0.0 초과 ~ 1.0)", required=True)

    class Meta:
        model = CarData
        fields = [
            'id', 'car_number', 'car_speed', 's3_key', 'image_url',
            'is_checked', 'created_at', 'updated_at',
            'x', 'y', 'w', 'h'  # 새 필드 추가
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']  #

    def validate(self, data):
        # ROI 좌표 유효성 검사 (0.0 ~ 1.0 범위 등)
        roi_x, roi_y, roi_w, roi_h = data.get('x'), data.get('y'), data.get('w'), data.get('h')

        if not (0.0 <= roi_x < 1.0):
            raise serializers.ValidationError({"x": "x 좌표는 0.0 이상 1.0 미만이어야 합니다."})
        if not (0.0 <= roi_y < 1.0):
            raise serializers.ValidationError({"y": "y 좌표는 0.0 이상 1.0 미만이어야 합니다."})
        if not (0.0 < roi_w <= 1.0):
            raise serializers.ValidationError({"w": "너비(w)는 0.0 초과 1.0 이하여야 합니다."})
        if not (0.0 < roi_h <= 1.0):
            raise serializers.ValidationError({"h": "높이(h)는 0.0 초과 1.0 이하여야 합니다."})

        if roi_x + roi_w > 1.00001:  # 부동소수점 오차 감안
            raise serializers.ValidationError("x 좌표와 너비(w)의 합이 1.0을 초과할 수 없습니다.")
        if roi_y + roi_h > 1.00001:
            raise serializers.ValidationError("y 좌표와 높이(h)의 합이 1.0을 초과할 수 없습니다.")

        return data