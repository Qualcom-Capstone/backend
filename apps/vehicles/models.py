from django.db import models


class Vehicle(models.Model):
    """차량 정보 (FCM 토큰 포함)"""
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


class DeviceToken(models.Model):
    """FCM 디바이스 토큰 (레거시 호환)"""
    token = models.CharField(max_length=255, unique=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crud_devicetoken'  # 기존 테이블 호환
        verbose_name = '디바이스 토큰'
        verbose_name_plural = '디바이스 토큰 목록'

    def __str__(self):
        return self.token[:50]

