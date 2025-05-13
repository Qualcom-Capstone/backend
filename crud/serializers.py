from rest_framework import serializers
from .models import CarData
from .tasks import send_speeding_alert # 파일명이 tasks.py 라면 from .tasks import send_speeding_alert 로 변경해주세요.

class CarDataSerializer(serializers.ModelSerializer):

    car_number = serializers.CharField(max_length=20, help_text="차량 고유 번호")
    car_speed = serializers.IntegerField(help_text="측정된 차량 속도 (km/h)")
    image_url = serializers.URLField(help_text="차량 이미지 URL")
    is_checked = serializers.BooleanField(default=False, help_text="확인 여부")

    class Meta:
        model = CarData
        fields = ['id', 'car_number', 'car_speed', 'image_url', 'is_checked', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']  # 읽기 전용 필드 지정

    def _trigger_speeding_alert_if_needed(self, instance):
        """
        인스턴스의 차량 속도를 확인하고, 70km/h를 초과하면 Celery 작업을 호출합니다.
        """
        # instance.car_speed가 None이 아니고, 숫자로 변환 가능한지 확인합니다.
        # serializers.IntegerField가 이미 정수형을 강제하지만, 안전을 위해 한 번 더 확인합니다.
        if instance.car_speed is not None:
            try:
                speed = int(instance.car_speed) # 모델 필드가 IntegerField라면 이미 정수형입니다.
                if speed > 70:
                    # Celery 작업 호출
                    # .delay()는 작업을 비동기적으로 실행하도록 Celery에 전달합니다.
                    print(f"차량번호: {instance.car_number}, 속도: {speed}km/h. 과속 감지, 알림 작업 요청.")
                    send_speeding_alert.delay(instance.car_number, speed)
            except ValueError:
                # car_speed가 숫자로 변환될 수 없는 경우 (IntegerField에서는 거의 발생하지 않음)
                print(f"경고: 차량 {instance.car_number}의 속도 값 '{instance.car_speed}'이(가) 유효한 숫자가 아닙니다.")
            except AttributeError:
                # instance에 car_number 또는 car_speed 속성이 없는 경우 (정상적인 모델이라면 발생하지 않음)
                print(f"경고: 인스턴스에 car_number 또는 car_speed 속성이 없습니다.")

    def create(self, validated_data):
        """
        새로운 CarData 인스턴스를 생성합니다.
        """
        instance = super().create(validated_data)
        self._trigger_speeding_alert_if_needed(instance)
        return instance

    def update(self, instance, validated_data):
        """
        기존 CarData 인스턴스를 업데이트합니다.
        """
        # validated_data를 사용하여 인스턴스를 먼저 업데이트합니다.
        # super().update()는 업데이트된 인스턴스를 반환합니다.
        instance = super().update(instance, validated_data)
        self._trigger_speeding_alert_if_needed(instance)
        return instance