from django.urls import path
from .views import UploadImageView, OcrResultDetailView, ProcessImageUrlView

urlpatterns = [
    path('upload/', UploadImageView.as_view(), name='upload_image'),
    path('process_url/', ProcessImageUrlView.as_view(), name='process_image_url'),
    path('result/<int:pk>/', OcrResultDetailView.as_view(), name='ocr_result_detail'),
]