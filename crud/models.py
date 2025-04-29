from django.db import models

# Create your models here.


class CarData(models.Model):
    car_number = models.CharField(max_length=20)
    car_speed = models.IntegerField()
    image_url = models.URLField()
    is_checked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']  # 기본적으로 최신 순으로 정렬

    def __str__(self):
        return self.car_number