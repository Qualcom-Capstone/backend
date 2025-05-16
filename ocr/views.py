from django.shortcuts import render, redirect
from django.views import View
from .forms import UploadImageForm, ImageUrlForm
from .models import OcrResult
import pytesseract
from PIL import Image
import requests
from io import BytesIO

class UploadImageView(View):
    def get(self, request):
        form = UploadImageForm()
        return render(request, 'ocr/upload_image.html', {'form': form})

    def post(self, request):
        form = UploadImageForm(request.POST, request.FILES)
        if form.is_valid():
            image_file = form.cleaned_data['image']
            ocr_result_text = self.perform_ocr(image_file)
            ocr_result = OcrResult.objects.create(image=image_file.name, text=ocr_result_text) # 파일 이름 저장
            return redirect('ocr_result_detail', ocr_result.id)
        return render(request, 'ocr/upload_image.html', {'form': form, 'error': '이미지 업로드에 실패했습니다.'})

    def perform_ocr(self, image_file):
        try:
            img = Image.open(image_file)
            text = pytesseract.image_to_string(img, lang='kor+eng')
            return text
        except Exception as e:
            return f"OCR 처리 오류: {e}"

class ProcessImageUrlView(View):
    def get(self, request):
        form = ImageUrlForm()
        return render(request, 'ocr/process_image_url.html', {'form': form})

    def post(self, request):
        form = ImageUrlForm(request.POST)
        if form.is_valid():
            image_url = form.cleaned_data['image_url']
            ocr_result_text = self.perform_ocr_from_url(image_url)
            ocr_result = OcrResult.objects.create(image=image_url, text=ocr_result_text)
            return redirect('ocr_result_detail', ocr_result.id)
        return render(request, 'ocr/process_image_url.html', {'form': form, 'error': '유효하지 않은 URL입니다.'})

    def perform_ocr_from_url(self, image_url):
        try:
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            text = pytesseract.image_to_string(image, lang='kor+eng')
            return text
        except requests.exceptions.RequestException as e:
            return f"이미지 다운로드 오류: {e}"
        except Exception as e:
            return f"OCR 처리 오류: {e}"

class OcrResultDetailView(View):
    def get(self, request, pk):
        try:
            ocr_result = OcrResult.objects.get(pk=pk)
            return render(request, 'ocr/ocr_result_detail.html', {'ocr_result': ocr_result})
        except OcrResult.DoesNotExist:
            return render(request, 'ocr/error.html', {'message': 'OCR 결과를 찾을 수 없습니다.'})