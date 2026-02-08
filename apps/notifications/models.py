from django.db import models


class Notification(models.Model):
    """
    알림 전송 이력

    MSA 구조: FK 대신 ID로 다른 서비스 데이터 참조
    - detection_id: Detections Service의 Detection ID
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    # MSA: FK 대신 ID로 참조 (Detections Service)
    detection_id = models.BigIntegerField(verbose_name="감지 내역 ID")
    fcm_token = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="FCM 토큰"
    )
    title = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="알림 제목"
    )
    body = models.TextField(blank=True, null=True, verbose_name="알림 내용")
    sent_at = models.DateTimeField(blank=True, null=True, verbose_name="전송 시간")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="상태"
    )
    retry_count = models.IntegerField(default=0, verbose_name="재시도 횟수")
    error_message = models.TextField(blank=True, null=True, verbose_name="에러 메시지")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "알림"
        verbose_name_plural = "알림 목록"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["detection_id"]),
            models.Index(fields=["status", "retry_count"]),
            models.Index(fields=["sent_at"]),
        ]

    def __str__(self):
        return f"Notification for Detection #{self.detection_id} - {self.status}"
