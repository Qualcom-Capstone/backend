from django.db import models
# DB에 어떤 데이터를 저장할지 스키마를 정의
# Create your models here.

class Vehicle(models.Model):
    plate_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

class SpeedViolation(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE) #외래키로 설정
    speed = models.IntegerField()
    location = models.CharField(max_length=255)
    timestamp = models.DateTimeField()