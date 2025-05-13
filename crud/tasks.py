from celery import shared_task
import logging
from django.conf import settings # Django 설정 임포트

logger = logging.getLogger(__name__)

@shared_task
def send_speeding_alert(car_number, car_speed):

    alert_message = f"경고: 차량 번호 {car_number}가 {car_speed}km/h로 과속 중입니다!"
    print(alert_message)
    logger.info(alert_message)

    try:
        db_settings = settings.DATABASES['default']
        # print(f"[CELERY TASK DEBUG] Django settings.DATABASES['default']['USER']: {db_settings.get('USER')}")
        # print(f"[CELERY TASK DEBUG] Django settings.DATABASES['default']['NAME']: {db_settings.get('NAME')}")
        # print(f"[CELERY TASK DEBUG] Django settings.DATABASES['default']['HOST']: {db_settings.get('HOST')}")
        # print(f"[CELERY TASK DEBUG] Django settings.DATABASES['default']['PASSWORD']: {db_settings.get('PASSWORD')}") # 비밀번호는 로그에 남기지 않는 것이 좋습니다.
    except Exception as e:
        print(f"[CELERY TASK DEBUG] Django 설정 접근 중 오류: {e}")
    # --- 디버깅 종료 ---

    # 여기에 실제 알림 로직을 추가할 수 있습니다:
    # - 이메일 발송
    # - SMS 발송
    # - 다른 시스템으로 API 호출
    # - 웹소켓을 통해 클라이언트에 실시간 알림 등

    return alert_message
