# models.py
from django.db import models

class CarData(models.Model):
    car_number = models.CharField(max_length=20, blank=True, null=True) # OCR 결과로 채워짐
    car_speed = models.IntegerField()
    gcs_key = models.CharField(max_length=512, unique=True)  # GCS blob name
    image_url = models.URLField()
    is_checked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    x = models.FloatField(null=True, blank=True, help_text="관심영역(ROI)의 상대 x 좌표")
    y = models.FloatField(null=True, blank=True, help_text="관심영역(ROI)의 상대 y 좌표")
    w = models.FloatField(null=True, blank=True, help_text="관심영역(ROI)의 상대 너비")
    h = models.FloatField(null=True, blank=True, help_text="관심영역(ROI)의 상대 높이")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.car_number if self.car_number else f"Data for {self.gcs_key}"

class NotificationLog(models.Model):
    car_data = models.ForeignKey(CarData, on_delete=models.CASCADE) #
    status = models.CharField(max_length=20) #
    response = models.TextField() #
    created_at = models.DateTimeField(auto_now_add=True) #

    class Meta: #
        ordering = ["-created_at"] #


class DeviceToken(models.Model):
    token = models.CharField(max_length=255, unique=True) #
    registered_at = models.DateTimeField(auto_now_add=True) #