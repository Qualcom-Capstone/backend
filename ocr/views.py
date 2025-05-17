# ocr/views.py

from django.shortcuts import render, redirect
from django.views import View
from .forms import UploadImageForm, ImageUrlForm
from .models import OcrResult
import pytesseract
from PIL import Image
import requests
from io import BytesIO
import cv2
import numpy as np
import re

# 한국 번호판에 사용될 수 있는 문자셋 (필요에 따라 계속 추가/수정)
# 최신 번호판 형식(숫자 2/3 + 한글 1 + 숫자 4) 및 이전 형식 고려
KOR_LICENSE_PLATE_CHARS = "0123456789가나다라마거너더러머버서어저고노도로모보소오조구누두루무부수우주배하허호육해공앞뒤발"
# 여기에 실제 번호판에 자주 등장하거나 Tesseract가 혼동하는 문자들을 추가


class UploadImageView(View):
    def get(self, request):
        form = UploadImageForm()
        return render(request, 'ocr/upload_image.html', {'form': form})

    def post(self, request):
        form = UploadImageForm(request.POST, request.FILES)
        if form.is_valid():
            image_file = form.cleaned_data['image']
            try:
                # PIL Image를 OpenCV 이미지로 변환
                pil_image = Image.open(image_file).convert('RGB') # RGB로 변환
                cv_image = np.array(pil_image)
                cv_image = cv_image[:, :, ::-1].copy() # RGB to BGR for OpenCV

                ocr_result_text = self.process_and_perform_ocr(cv_image)
                # 파일 이름 대신 "Uploaded Image" 또는 URL을 저장하도록 수정 (models.py 변경과 일치)
                ocr_result = OcrResult.objects.create(image=f"Uploaded: {image_file.name}", text=ocr_result_text)
                return redirect('ocr_result_detail', ocr_result.id)

            except Exception as e:
                # OCR 처리 중 발생한 모든 예외를 처리
                return render(request, 'ocr/upload_image.html', {'form': form, 'error': f'이미지 처리 또는 OCR 오류: {str(e)}'})

        return render(request, 'ocr/upload_image.html', {'form': form, 'error': '이미지 업로드에 실패했습니다.'})

    def process_and_perform_ocr(self, cv_image):
        # --- 1. (선택적이지만 중요) 번호판 영역 자동 검출 ---
        # 실제 프로덕션 환경에서는 이 부분에 번호판 위치를 찾는 알고리즘이 들어가야 합니다.
        # 예: OpenCV Haar Cascade, YOLO 등 딥러닝 기반 객체 탐지 모델
        # 아래는 전체 이미지를 대상으로 처리하지만, 실제로는 검출된 ROI를 사용해야 합니다.
        # plate_roi_image = detect_license_plate(cv_image) # 가상의 함수
        # if plate_roi_image is None:
        #     return "번호판 영역을 찾지 못했습니다."
        # gray_img = cv2.cvtColor(plate_roi_image, cv2.COLOR_BGR2GRAY)

        # 현재는 전체 이미지를 사용한다고 가정
        gray_img = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        # --- 2. 이미지 전처리 ---
        # A. 가우시안 블러로 노이즈 감소 (Otsu 이진화 전에 적용하면 좋음)
        blurred_img = cv2.GaussianBlur(gray_img, (5, 5), 0)

        # B. 이진화 (Otsu의 이진화 또는 적응형 스레시홀딩)
        #_, binary_img = cv2.threshold(blurred_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 또는 번호판의 밝기나 그림자에 따라 적응형 스레시홀딩이 더 좋을 수 있습니다.
        binary_img = cv2.adaptiveThreshold(
            blurred_img, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, # 또는 cv2.ADAPTIVE_THRESH_MEAN_C
            cv2.THRESH_BINARY_INV, # 번호판 글자가 어둡고 배경이 밝은 경우 또는 그 반대의 경우에 따라 THRESH_BINARY 또는 THRESH_BINARY_INV
            11, # 블록 크기 (홀수)
            2   # 평균 또는 가중 평균에서 뺄 상수 C
        )
        # 만약 글자가 흰색이고 배경이 검은색으로 이진화되었다면, 반전시켜줍니다.
        # (Tesseract는 주로 검은 글자/흰 배경을 선호)
        if np.mean(binary_img) > 127: # 이미지 평균 밝기가 높으면 (배경이 흰색이면)
           binary_img = cv2.bitwise_not(binary_img) # 반전 (글자 검정, 배경 흰색)

        # C. (선택적) 모폴로지 연산 (노이즈 제거, 글자 굵게/얇게)
        # kernel = np.ones((1,1), np.uint8)
        # binary_img = cv2.erode(binary_img, kernel, iterations=1)
        # binary_img = cv2.dilate(binary_img, kernel, iterations=1)

        # D. (선택적) 이미지 리사이징 (너무 작거나 크면 성능 저하)
        target_height = 100 # 예시 높이
        if binary_img.shape[0] < target_height:
            scale_factor = target_height / binary_img.shape[0]
            width = int(binary_img.shape[1] * scale_factor)
            binary_img = cv2.resize(binary_img, (width, target_height), interpolation=cv2.INTER_CUBIC)

        # --- 3. Pytesseract OCR 수행 ---
        # Tesseract 설정:
        # --oem 3: 기본 OCR 엔진 모드 (LSTM 포함)
        # --psm 7: 이미지를 단일 텍스트 라인으로 취급 (번호판에 적합할 수 있음)
        # 다른 psm 값도 테스트해보세요: psm 6 (단일 블록), psm 8 (단일 단어), psm 13 (raw line)
        custom_config = f'--oem 3 --psm 8 -l kor -c tessedit_char_whitelist={KOR_LICENSE_PLATE_CHARS}'

        try:
            # 전처리된 이미지(NumPy 배열)를 바로 Tesseract에 전달
            text = pytesseract.image_to_string(binary_img, config=custom_config)

            # --- 4. OCR 결과 후처리 ---
            # 인식된 텍스트에서 공백, 특수문자 제거 (필요에 따라 정규식 강화)
            cleaned_text = re.sub(r'[^0-9가-힣]', '', text).strip()
            # 번호판 형식에 맞게 더 정교한 필터링 가능 (예: 숫자 + 한글 + 숫자 조합)
            # 예시: 연속된 숫자, 한글, 숫자로만 구성된 문자열 추출
            matches = re.findall(r'[0-9가-힣]+', text)
            cleaned_text = "".join(matches)
            # 번호판 패턴에 안 맞는 짧은 노이즈 제거 (예: 3글자 미만이면 무시)
            if len(cleaned_text) < 3:
                cleaned_text = "인식된 텍스트가 너무 짧습니다."

            # 디버깅용: 어떤 이미지가 어떻게 처리되었는지 확인
            # cv2.imwrite(f"debug_gray_{image_file.name if hasattr(image_file, 'name') else 'url_image'}.png", gray_img)
            # cv2.imwrite(f"debug_binary_{image_file.name if hasattr(image_file, 'name') else 'url_image'}.png", binary_img)
            # print(f"Raw OCR text: {text}")
            # print(f"Cleaned OCR text: {cleaned_text}")
            return cleaned_text if cleaned_text else "텍스트를 인식하지 못했습니다."

        except pytesseract.TesseractError as e:
            return f"Tesseract OCR 오류: {e}"
        except Exception as e:
            return f"OCR 처리 중 알 수 없는 오류: {e}"


class ProcessImageUrlView(View):
    def get(self, request):
        form = ImageUrlForm()
        return render(request, 'ocr/process_image_url.html', {'form': form})

    def post(self, request):
        form = ImageUrlForm(request.POST)
        if form.is_valid():
            image_url = form.cleaned_data['image_url']
            try:
                response = requests.get(image_url, stream=True, timeout=10) # 타임아웃 추가
                response.raise_for_status() # HTTP 오류 발생 시 예외 발생

                # PIL Image를 OpenCV 이미지로 변환
                pil_image = Image.open(BytesIO(response.content)).convert('RGB')
                cv_image = np.array(pil_image)
                cv_image = cv_image[:, :, ::-1].copy() # RGB to BGR

                # UploadImageView와 동일한 OCR 처리 로직 사용
                # UploadImageView의 인스턴스를 만들거나, process_and_perform_ocr을 staticmethod 또는 별도 유틸 함수로 분리
                # 여기서는 간단하게 UploadImageView의 인스턴스를 생성하여 호출
                upload_view_instance = UploadImageView()
                ocr_result_text = upload_view_instance.process_and_perform_ocr(cv_image)

                ocr_result = OcrResult.objects.create(image=image_url, text=ocr_result_text)
                return redirect('ocr_result_detail', ocr_result.id)
            except requests.exceptions.RequestException as e:
                return render(request, 'ocr/process_image_url.html', {'form': form, 'error': f'이미지 다운로드 오류: {e}'})
            except Exception as e: # OCR 처리 중 발생한 모든 예외를 처리
                return render(request, 'ocr/process_image_url.html', {'form': form, 'error': f'이미지 처리 또는 OCR 오류: {str(e)}'})
        return render(request, 'ocr/process_image_url.html', {'form': form, 'error': '유효하지 않은 URL입니다.'})


class OcrResultDetailView(View):
    def get(self, request, pk):
        try:
            ocr_result = OcrResult.objects.get(pk=pk)
            return render(request, 'ocr/ocr_result_detail.html', {'ocr_result': ocr_result})
        except OcrResult.DoesNotExist:
            return render(request, 'ocr/error.html', {'message': 'OCR 결과를 찾을 수 없습니다.'})