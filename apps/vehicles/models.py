from django.db import models


class Vehicle(models.Model):
    """
    차량 정보 (FCM 토큰 포함)
    
    MSA 구조: vehicles_db에 저장
    """
    plate_number = models.CharField(
        max_length=20, 
        unique=True, 
        verbose_name='차량 번호'
    )
    owner_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='소유자명'
    )
    owner_phone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name='연락처'
    )
    fcm_token = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name='FCM 토큰'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vehicles'
        verbose_name = '차량'
        verbose_name_plural = '차량 목록'
        indexes = [
            models.Index(fields=['plate_number']),
            models.Index(fields=['fcm_token']),
        ]

    def __str__(self):
        return self.plate_number
