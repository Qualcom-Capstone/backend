FROM python:3.10

# 작업 디렉토리 설정
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1-mesa-glx \
      libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt .

RUN apt-get update
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
# 소스 코드 복사
COPY . .
