from django.db import models


class Detection(models.Model):
    """과속 감지 내역"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    vehicle = models.ForeignKey(
        'vehicles.Vehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='detections',
        verbose_name='차량'
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
            models.Index(fields=['vehicle']),
            models.Index(fields=['detected_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['camera_id', 'detected_at']),
        ]

    def __str__(self):
        return f"{self.ocr_result or 'Unknown'} - {self.detected_speed}km/h"


class CarData(models.Model):
    """레거시 모델 (기존 crud 호환)"""
    car_number = models.CharField(max_length=20, blank=True, null=True)
    car_speed = models.IntegerField()
    gcs_key = models.CharField(max_length=512, unique=True)
    image_url = models.URLField()
    is_checked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    w = models.FloatField(null=True, blank=True)
    h = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'crud_cardata'  # 기존 테이블 호환
        ordering = ['-created_at']
        verbose_name = '차량 데이터 (레거시)'
        verbose_name_plural = '차량 데이터 목록 (레거시)'

    def __str__(self):
        return self.car_number if self.car_number else f"Data for {self.gcs_key}"

