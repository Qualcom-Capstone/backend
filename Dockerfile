FROM python:3.10

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (Tesseract OCR, OpenCV 의존성, 한국어 OCR 데이터)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사
COPY requirements.txt .

# pip 업그레이드 및 requirements.txt 에 명시된 Python 패키지 설치
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt # --no-cache-dir 옵션으로 이미지 크기 최적화

# 소스 코드 복사
COPY . .

