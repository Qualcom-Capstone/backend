from django.db import models

class OcrResult(models.Model):
    image = models.CharField(max_length=255)  # URL 저장을 위해 CharField로 변경
    text = models.TextField()
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OCR Result for {self.image}"