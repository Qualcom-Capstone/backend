from django.db import models


class Detection(models.Model):
    """
    과속 감지 내역
    
    MSA 구조: FK 대신 ID로 다른 서비스 데이터 참조
    - vehicle_id: Vehicles Service의 Vehicle ID
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # MSA: FK 대신 ID로 참조 (Vehicles Service)
    vehicle_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='차량 ID'
    )
    detected_speed = models.FloatField(verbose_name='감지 속도')
    speed_limit = models.FloatField(default=60.0, verbose_name='제한 속도')
    location = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name='위치'
    )
    camera_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name='카메라 ID'
    )
    image_gcs_uri = models.CharField(
        max_length=500, 
        verbose_name='GCS 이미지 경로'
    )
    ocr_result = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name='OCR 결과'
    )
    ocr_confidence = models.FloatField(
        blank=True, 
        null=True,
        verbose_name='OCR 신뢰도'
    )
    detected_at = models.DateTimeField(verbose_name='감지 시간')
    processed_at = models.DateTimeField(
        blank=True, 
        null=True,
        verbose_name='처리 완료 시간'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='상태'
    )
    error_message = models.TextField(
        blank=True, 
        null=True,
        verbose_name='에러 메시지'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'detections'
        verbose_name = '감지 내역'
        verbose_name_plural = '감지 내역 목록'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['vehicle_id']),
            models.Index(fields=['detected_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['camera_id', 'detected_at']),
        ]

    def __str__(self):
        return f"{self.ocr_result or 'Unknown'} - {self.detected_speed}km/h"
