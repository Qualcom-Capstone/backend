from django.db import models

# Create your models here.


class CarData(models.Model):
    car_number = models.CharField(max_length=20)
    car_speed = models.IntegerField()
    s3_key = models.CharField(max_length=512, unique=True)
    image_url = models.URLField()
    is_checked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']  # 기본적으로 최신 순으로 정렬

    def __str__(self):
        return self.car_number

class NotificationLog(models.Model):
    car_data = models.ForeignKey(CarData, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)  # SUCCESS / RETRY / DLQ
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

# models.py
class DeviceToken(models.Model):
    token = models.CharField(max_length=255, unique=True)
    registered_at = models.DateTimeField(auto_now_add=True)


