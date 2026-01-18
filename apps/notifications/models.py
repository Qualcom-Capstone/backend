from django.db import models


class Notification(models.Model):
    """알림 전송 이력"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    detection = models.ForeignKey(
        'detections.Detection',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='감지 내역'
    )
    fcm_token = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name='FCM 토큰'
    )
    title = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name='알림 제목'
    )
    body = models.TextField(
        blank=True, 
        null=True,
        verbose_name='알림 내용'
    )
    sent_at = models.DateTimeField(
        blank=True, 
        null=True,
        verbose_name='전송 시간'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='상태'
    )
    retry_count = models.IntegerField(default=0, verbose_name='재시도 횟수')
    error_message = models.TextField(
        blank=True, 
        null=True,
        verbose_name='에러 메시지'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = '알림'
        verbose_name_plural = '알림 목록'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['detection']),
            models.Index(fields=['status', 'retry_count']),
            models.Index(fields=['sent_at']),
        ]

    def __str__(self):
        return f"Notification for Detection #{self.detection_id} - {self.status}"


class NotificationLog(models.Model):
    """레거시 알림 로그 (기존 crud 호환)"""
    car_data = models.ForeignKey(
        'detections.CarData',
        on_delete=models.CASCADE
    )
    status = models.CharField(max_length=20)
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crud_notificationlog'  # 기존 테이블 호환
        ordering = ['-created_at']
        verbose_name = '알림 로그 (레거시)'
        verbose_name_plural = '알림 로그 목록 (레거시)'

    def __str__(self):
        return f"Log for CarData #{self.car_data_id} - {self.status}"

