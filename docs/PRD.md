# 과속 차량 감지 및 알림 시스템 PRD

## 1. 프로젝트 개요

### 1.1 목적
라즈베리파이 기반 엣지 디바이스에서 과속 차량을 감지하고, 번호판 OCR 인식 후 차량 소유자에게 실시간 푸시 알림을 전송하는 시스템

### 1.2 핵심 기능
- 과속 차량 이미지 수집 및 저장 (GCS)
- 번호판 OCR 인식 (EasyOCR)
- FCM 푸시 알림 전송
- 위반 내역 조회 API

---

## 2. 시스템 아키텍처

### 2.1 아키텍처 패턴
- **Event-Driven Microservices (Choreography Pattern)**
- 각 서비스가 자율적으로 DB를 업데이트하고 다음 이벤트를 발행

### 2.2 인스턴스 배포 구조

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GCP Infrastructure                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  Main Instance  │    │  OCR Instance   │    │ Alert Instance  │         │
│  │   (Django)      │    │ (Celery Worker) │    │ (Celery Worker) │         │
│  │                 │    │                 │    │                 │         │
│  │ - API Server    │    │ - OCR Task      │    │ - FCM Task      │         │
│  │ - MQTT Sub      │    │ - GCS Download  │    │ - Push Notify   │         │
│  │ - Task Dispatch │    │ - DB Update     │    │ - DB Update     │         │
│  │ - DataDog Agent │    │ - DataDog Agent │    │ - DataDog Agent │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           └──────────────────────┼──────────────────────┘                   │
│                                  │                                          │
│                     ┌────────────▼────────────┐                             │
│                     │   RabbitMQ Instance     │                             │
│                     │   (Message Broker)      │                             │
│                     │   - MQTT Plugin         │                             │
│                     │   - AMQP Queues         │                             │
│                     │   - DataDog Agent       │                             │
│                     └────────────┬────────────┘                             │
│                                  │                                          │
│                     ┌────────────▼────────────┐                             │
│                     │   Cloud SQL (MySQL)     │                             │
│                     └─────────────────────────┘                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 아키텍처 다이어그램

```mermaid
graph TB
    subgraph Edge["Edge Device"]
        Pi[Raspberry Pi]
    end
    
    subgraph GCP["Google Cloud Platform"]
        GCS[(Cloud Storage)]
        
        subgraph RMQ["RabbitMQ Instance"]
            MQTT[MQTT Plugin<br/>Port 1883]
            AMQP[AMQP Broker<br/>Port 5672]
        end
        
        subgraph Main["Main Instance"]
            Django[Django App<br/>Ingestion & API]
            DD1[DataDog Agent]
        end
        
        subgraph OCRInst["OCR Instance"]
            OCR[OCR Worker<br/>Celery]
            DD2[DataDog Agent]
        end
        
        subgraph AlertInst["Alert Instance"]
            FCM[Notification Worker<br/>Celery]
            DD3[DataDog Agent]
        end
        
        MySQL[(Cloud SQL<br/>MySQL)]
        DD4[DataDog Agent]
    end
    
    subgraph External["External Services"]
        Firebase[Firebase FCM]
        DataDog[DataDog Cloud]
    end
    
    Pi -->|1. 이미지 업로드| GCS
    Pi -->|2. MQTT Publish| MQTT
    MQTT -->|3. MQTT Subscribe| Django
    Django -->|4. pending 레코드| MySQL
    Django -->|5. AMQP Publish| AMQP
    AMQP -->|ocr_queue| OCR
    OCR -->|6. 이미지 다운로드| GCS
    OCR -->|7. 결과 업데이트| MySQL
    OCR -->|8. AMQP Publish| AMQP
    AMQP -->|fcm_queue| FCM
    FCM -->|9. 토큰 조회| MySQL
    FCM -->|10. 푸시 전송| Firebase
    FCM -->|11. 이력 저장| MySQL
    
    DD1 --> DataDog
    DD2 --> DataDog
    DD3 --> DataDog
    DD4 --> DataDog
```

### 2.4 이벤트 흐름 (Sequence Diagram)

```mermaid
sequenceDiagram
    participant Pi as Raspberry Pi
    participant GCS as Cloud Storage
    participant MQTT as RabbitMQ MQTT
    participant Django as Main Service
    participant AMQP as RabbitMQ AMQP
    participant OCR as OCR Service
    participant FCM as Alert Service
    participant DB as MySQL

    Note over Pi: 과속 차량 감지
    Pi->>GCS: 1. 이미지 업로드
    Pi->>MQTT: 2. MQTT Publish (detections/new)
    
    MQTT->>Django: 3. MQTT Subscribe
    Django->>DB: 4. Detection 생성 (status=pending)
    Django->>AMQP: 5. Publish to ocr_exchange (Direct)
    
    AMQP->>OCR: 6. Consume from ocr_queue
    OCR->>GCS: 7. 이미지 다운로드
    OCR->>OCR: 8. EasyOCR 실행
    OCR->>DB: 9. 직접 업데이트 (status=completed)
    OCR->>AMQP: 10. Publish to fcm_exchange (Direct)
    
    AMQP->>FCM: 11. Consume from fcm_queue
    FCM->>DB: 12. FCM 토큰 조회
    FCM->>FCM: 13. FCM API 호출
    FCM->>DB: 14. 알림 이력 저장
```

---

## 3. 기술 스택

### 3.1 Backend
| 구분 | 기술 | 버전 |
|------|------|------|
| Language | Python | 3.13+ |
| Framework | Django | 5.1.7 |
| API | Django REST Framework | 3.15.2 |
| WSGI Server | Gunicorn | 23.0.0 |
| Task Queue | Celery | 5.5.2 |
| Message Broker | RabbitMQ | 3.13+ |

### 3.2 Database & Storage
| 구분 | 기술 | 버전 |
|------|------|------|
| RDBMS | MySQL | 8.0 |
| MySQL Connector | PyMySQL | 1.1.1 |
| Object Storage | Google Cloud Storage | 2.18.2 |
| Push Notification | Firebase Admin SDK | 6.8.0 |

### 3.3 OCR & Image Processing
| 구분 | 기술 | 버전 |
|------|------|------|
| OCR Engine | EasyOCR | 1.7.2 |
| Image Processing | OpenCV | 4.10.0.84 |
| Image Library | Pillow | 11.2.1 |

### 3.4 Monitoring
| 구분 | 기술 | 용도 |
|------|------|------|
| APM | DataDog | Django, Celery 성능 모니터링 |
| Infrastructure | DataDog Agent | 서버 메트릭 수집 |
| Message Queue | DataDog RabbitMQ Integration | Queue 모니터링 |

---

## 4. RabbitMQ 메시징 설계

### 4.1 프로토콜 활용 전략

```mermaid
graph LR
    subgraph MQTT["MQTT (Port 1883)"]
        direction TB
        M1[Raspberry Pi] -->|Publish| M2[detections/new]
        M2 -->|Subscribe| M3[Django]
    end
    
    subgraph AMQP["AMQP (Port 5672)"]
        direction TB
        A1[Django] -->|Publish| A2[ocr_exchange]
        A2 -->|Route| A3[ocr_queue]
        A3 -->|Consume| A4[OCR Worker]
        
        A4 -->|Publish| A5[fcm_exchange]
        A5 -->|Route| A6[fcm_queue]
        A6 -->|Consume| A7[Alert Worker]
    end
```

| 프로토콜 | 용도 | 특징 |
|----------|------|------|
| **MQTT** | Raspberry Pi → Django | 경량 프로토콜, IoT 디바이스에 적합, QoS 1 |
| **AMQP** | Django ↔ Celery Workers | 안정적인 메시지 전달, Exchange/Queue 라우팅 |

### 4.2 Exchange 설계

| Exchange | Type | Routing Key | 용도 |
|----------|------|-------------|------|
| `ocr_exchange` | **Direct** | `ocr` | OCR Task 라우팅 |
| `fcm_exchange` | **Direct** | `fcm` | 알림 Task 라우팅 |
| `dlq_exchange` | **Fanout** | - | Dead Letter 처리 |

**Direct Exchange 선택 이유:**
- 1:1 라우팅으로 명확한 Task 분배
- Routing Key 기반 정확한 Queue 매핑
- Topic Exchange보다 단순하고 오버헤드 적음

### 4.3 Queue 설계

```python
# RabbitMQ Queue 설정
QUEUES = {
    'ocr_queue': {
        'exchange': 'ocr_exchange',
        'exchange_type': 'direct',
        'routing_key': 'ocr',
        'durable': True,
        'arguments': {
            'x-dead-letter-exchange': 'dlq_exchange',
            'x-dead-letter-routing-key': 'dlq',
            'x-message-ttl': 3600000,  # 1시간
            'x-max-priority': 10,
        }
    },
    'fcm_queue': {
        'exchange': 'fcm_exchange',
        'exchange_type': 'direct',
        'routing_key': 'fcm',
        'durable': True,
        'arguments': {
            'x-dead-letter-exchange': 'dlq_exchange',
            'x-dead-letter-routing-key': 'dlq',
            'x-message-ttl': 3600000,  # 1시간
        }
    },
    'dlq_queue': {
        'exchange': 'dlq_exchange',
        'exchange_type': 'fanout',
        'routing_key': '',
        'durable': True,
    }
}
```

### 4.4 Queue 설정 상세

| Queue | Durable | TTL | Max Priority | DLQ | Prefetch |
|-------|---------|-----|--------------|-----|----------|
| `ocr_queue` | ✅ | 1시간 | 10 | ✅ | 1 |
| `fcm_queue` | ✅ | 1시간 | - | ✅ | 10 |
| `dlq_queue` | ✅ | - | - | - | 1 |

**Prefetch 설정 이유:**
- `ocr_queue`: 1 (CPU 집약적, 한 번에 하나씩 처리)
- `fcm_queue`: 10 (I/O 대기 시간 활용)

### 4.5 RabbitMQ MQTT Plugin 설정

```conf
# rabbitmq.conf
mqtt.listeners.tcp.default = 1883
mqtt.allow_anonymous = false
mqtt.default_user = mqtt_user
mqtt.default_pass = mqtt_pass
mqtt.vhost = /
mqtt.exchange = amq.topic
mqtt.subscription_ttl = 86400000
mqtt.prefetch = 10
```

### 4.6 메시지 흐름

```
[Raspberry Pi]
    │
    │ MQTT Publish
    │ Topic: detections/new
    │ QoS: 1
    ▼
[RabbitMQ MQTT Plugin]
    │
    │ 내부 변환 (MQTT → AMQP)
    │ Exchange: amq.topic
    │ Routing Key: detections.new
    ▼
[Django MQTT Subscriber]
    │
    │ 메시지 수신 & 처리
    │ Detection 생성
    │
    │ AMQP Publish
    │ Exchange: ocr_exchange
    │ Routing Key: ocr
    ▼
[ocr_queue]
    │
    │ Consumer: OCR Worker
    ▼
[OCR Worker]
    │
    │ 처리 완료
    │ AMQP Publish
    │ Exchange: fcm_exchange
    │ Routing Key: fcm
    ▼
[fcm_queue]
    │
    │ Consumer: Alert Worker
    ▼
[Alert Worker]
    │
    │ FCM 전송 완료
    ▼
[End]
```

---

## 5. Trade-off 분석

### 5.1 Choreography vs Orchestration

| 항목 | Choreography (선택) | Orchestration |
|------|---------------------|---------------|
| **구조** | 각 서비스가 자율적으로 동작 | 중앙 Orchestrator가 제어 |
| **결합도** | 느슨한 결합 ✅ | 강한 결합 |
| **확장성** | 서비스별 독립 확장 ✅ | Orchestrator 병목 가능 |
| **장애 격리** | 한 서비스 장애가 전체에 영향 적음 ✅ | 중앙 장애 시 전체 중단 |
| **디버깅** | 흐름 추적 어려움 | 중앙에서 추적 용이 |
| **복잡도** | 이벤트 설계 복잡 | 로직 집중 관리 |

**선택 이유:**
- 각 인스턴스(Main, OCR, Alert)가 독립적으로 배포/확장
- OCR Worker가 직접 DB 업데이트 → 지연 시간 감소
- 서비스 간 느슨한 결합으로 장애 격리

### 5.2 RabbitMQ vs Google Cloud Pub/Sub

| 항목 | RabbitMQ (선택) | Cloud Pub/Sub |
|------|-----------------|---------------|
| **MQTT 지원** | Plugin으로 지원 ✅ | 미지원 (별도 브릿지 필요) |
| **지연 시간** | 낮음 (VPC 내부) ✅ | 상대적으로 높음 |
| **비용** | 인스턴스 비용만 ✅ | 메시지 수 기반 과금 |
| **Exchange 라우팅** | 유연한 라우팅 ✅ | 단순 Topic 기반 |
| **Priority Queue** | 지원 ✅ | 미지원 |
| **관리 부담** | 직접 운영 필요 | 완전 관리형 |
| **확장성** | 클러스터링 필요 | 자동 확장 |

**선택 이유:**
- Raspberry Pi가 MQTT 프로토콜 사용 → RabbitMQ MQTT Plugin 활용
- Priority Queue로 긴급 이벤트 우선 처리
- Exchange 기반 유연한 라우팅
- VPC 내부 통신으로 낮은 지연 시간

### 5.3 prefork vs gevent Pool

| 항목 | prefork | gevent |
|------|---------|--------|
| **방식** | 멀티프로세싱 | 코루틴 (Greenlet) |
| **GIL 영향** | 회피 가능 ✅ | 영향 받음 |
| **적합한 작업** | CPU-bound ✅ | I/O-bound ✅ |
| **메모리 사용** | 프로세스당 격리 | 경량 |
| **동시성** | 프로세스 수 제한 | 수천 개 가능 |

**적용 전략:**

| Worker | Pool | 이유 |
|--------|------|------|
| OCR Worker | `prefork` | EasyOCR은 CPU 집약적, GIL 회피 필요 |
| Alert Worker | `gevent` | FCM API 호출은 I/O 대기, 높은 동시성 필요 |

```python
# OCR Worker 실행
celery -A config worker --pool=prefork --concurrency=4 --queues=ocr_queue

# Alert Worker 실행
celery -A config worker --pool=gevent --concurrency=100 --queues=fcm_queue
```

---

## 6. 프로젝트 구조 (분리 배포용)

### 6.1 Monorepo 구조

각 서비스는 **동일한 코드베이스**를 공유하되, 실행 시 역할에 따라 다른 컴포넌트만 활성화합니다.

```
speedcam/
├── docker/
│   ├── Dockerfile.main          # Main Service (Django)
│   ├── Dockerfile.ocr           # OCR Service (Celery)
│   ├── Dockerfile.alert         # Alert Service (Celery)
│   └── docker-compose.yml       # 로컬 개발용
│
├── config/
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py              # 공통 설정
│   │   ├── dev.py               # 개발 환경
│   │   └── prod.py              # 운영 환경
│   ├── celery.py                # Celery 설정
│   ├── urls.py
│   └── wsgi.py
│
├── apps/                        # Django Apps (모든 서비스 공유)
│   ├── __init__.py
│   ├── vehicles/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── detections/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   └── notifications/
│       ├── __init__.py
│       ├── models.py
│       ├── serializers.py
│       └── views.py
│
├── tasks/                       # Celery Tasks
│   ├── __init__.py
│   ├── ocr_tasks.py             # OCR Service 전용
│   └── notification_tasks.py    # Alert Service 전용
│
├── core/                        # 공통 유틸리티
│   ├── __init__.py
│   ├── mqtt/
│   │   ├── __init__.py
│   │   └── subscriber.py        # Main Service 전용
│   ├── gcs/
│   │   ├── __init__.py
│   │   └── client.py            # GCS 클라이언트
│   ├── firebase/
│   │   ├── __init__.py
│   │   └── fcm.py               # FCM 클라이언트
│   └── datadog/
│       ├── __init__.py
│       └── tracer.py            # DataDog 트레이싱
│
├── scripts/
│   ├── start_main.sh            # Main Service 시작
│   ├── start_ocr_worker.sh      # OCR Worker 시작
│   └── start_alert_worker.sh    # Alert Worker 시작
│
├── manage.py
├── requirements/
│   ├── base.txt                 # 공통 의존성
│   ├── main.txt                 # Main Service 의존성
│   ├── ocr.txt                  # OCR Service 의존성
│   └── alert.txt                # Alert Service 의존성
│
└── .env.example
```

### 6.2 서비스별 의존성

**requirements/base.txt** (공통)
```txt
Django==5.1.7
djangorestframework==3.15.2
celery==5.5.2
PyMySQL==1.1.1
python-dotenv==1.0.1
ddtrace==2.6.0
```

**requirements/main.txt** (Main Service)
```txt
-r base.txt
gunicorn==23.0.0
paho-mqtt==2.0.0
django-cors-headers==4.7.0
drf-yasg==1.21.10
```

**requirements/ocr.txt** (OCR Service)
```txt
-r base.txt
easyocr==1.7.2
opencv-python-headless==4.10.0.84
pillow==11.2.1
google-cloud-storage==2.18.2
gevent==24.2.1
```

**requirements/alert.txt** (Alert Service)
```txt
-r base.txt
firebase-admin==6.8.0
gevent==24.2.1
```

### 6.3 서비스별 Dockerfile

**docker/Dockerfile.main**
```dockerfile
FROM python:3.13-slim

WORKDIR /app

# 의존성 설치
COPY requirements/base.txt requirements/main.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/main.txt

# 앱 복사
COPY . .

# DataDog Agent 설치
RUN DD_API_KEY=${DD_API_KEY} DD_INSTALL_ONLY=true \
    bash -c "$(curl -L https://s3.amazonaws.com/dd-agent/scripts/install_script.sh)"

EXPOSE 8000

CMD ["sh", "scripts/start_main.sh"]
```

**docker/Dockerfile.ocr**
```dockerfile
FROM python:3.13-slim

WORKDIR /app

# 시스템 의존성 (OpenCV)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements/base.txt requirements/ocr.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/ocr.txt

# 앱 복사
COPY . .

CMD ["sh", "scripts/start_ocr_worker.sh"]
```

**docker/Dockerfile.alert**
```dockerfile
FROM python:3.13-slim

WORKDIR /app

# 의존성 설치
COPY requirements/base.txt requirements/alert.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/alert.txt

# 앱 복사
COPY . .

CMD ["sh", "scripts/start_alert_worker.sh"]
```

### 6.4 서비스 시작 스크립트

**scripts/start_main.sh**
```bash
#!/bin/bash
set -e

# DataDog APM 활성화
export DD_SERVICE="speedcam-main"
export DD_ENV="${ENVIRONMENT:-dev}"

# Django 마이그레이션
python manage.py migrate --noinput

# MQTT Subscriber 백그라운드 실행
python -c "from core.mqtt.subscriber import MQTTSubscriber; MQTTSubscriber().start()" &

# Gunicorn 시작 (DataDog 트레이싱)
ddtrace-run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --threads 2 \
    --access-logfile -
```

**scripts/start_ocr_worker.sh**
```bash
#!/bin/bash
set -e

# DataDog APM 활성화
export DD_SERVICE="speedcam-ocr"
export DD_ENV="${ENVIRONMENT:-dev}"

# Celery Worker 시작 (prefork pool)
ddtrace-run celery -A config worker \
    --pool=prefork \
    --concurrency=${OCR_CONCURRENCY:-4} \
    --queues=ocr_queue \
    --hostname=ocr@%h \
    --loglevel=info
```

**scripts/start_alert_worker.sh**
```bash
#!/bin/bash
set -e

# DataDog APM 활성화
export DD_SERVICE="speedcam-alert"
export DD_ENV="${ENVIRONMENT:-dev}"

# Celery Worker 시작 (gevent pool)
ddtrace-run celery -A config worker \
    --pool=gevent \
    --concurrency=${ALERT_CONCURRENCY:-100} \
    --queues=fcm_queue \
    --hostname=alert@%h \
    --loglevel=info
```

---

## 7. DataDog 모니터링 설정

### 7.1 모니터링 구성도

```mermaid
graph TB
    subgraph Services["Application Services"]
        Main[Main Service<br/>ddtrace-run gunicorn]
        OCR[OCR Worker<br/>ddtrace-run celery]
        Alert[Alert Worker<br/>ddtrace-run celery]
    end
    
    subgraph Agents["DataDog Agents"]
        A1[Agent - Main Instance]
        A2[Agent - OCR Instance]
        A3[Agent - Alert Instance]
        A4[Agent - RabbitMQ Instance]
    end
    
    subgraph DataDog["DataDog Cloud"]
        APM[APM<br/>Traces]
        Metrics[Infrastructure<br/>Metrics]
        Logs[Log Management]
        Dash[Dashboards]
    end
    
    Main --> A1
    OCR --> A2
    Alert --> A3
    RMQ[RabbitMQ] --> A4
    
    A1 --> APM
    A2 --> APM
    A3 --> APM
    A4 --> Metrics
    
    A1 --> Metrics
    A2 --> Metrics
    A3 --> Metrics
    
    A1 --> Logs
    A2 --> Logs
    A3 --> Logs
```

### 7.2 DataDog Agent 설정

각 인스턴스에 DataDog Agent를 설치하고 설정합니다.

#### Main Instance (Django)

**datadog.yaml**
```yaml
# /etc/datadog-agent/datadog.yaml
api_key: ${DD_API_KEY}
site: datadoghq.com
hostname: speedcam-main

# APM 활성화
apm_config:
  enabled: true
  apm_non_local_traffic: true

# 로그 수집 활성화
logs_enabled: true

# 프로세스 모니터링
process_config:
  enabled: true

tags:
  - env:${ENVIRONMENT}
  - service:speedcam-main
  - team:backend
```

**conf.d/gunicorn.d/conf.yaml**
```yaml
# Gunicorn 메트릭 수집
init_config:

instances:
  - proc_name: gunicorn
    access_log: /var/log/gunicorn/access.log
    error_log: /var/log/gunicorn/error.log
```

#### OCR Instance (Celery)

**datadog.yaml**
```yaml
api_key: ${DD_API_KEY}
site: datadoghq.com
hostname: speedcam-ocr

apm_config:
  enabled: true
  apm_non_local_traffic: true

logs_enabled: true

process_config:
  enabled: true

tags:
  - env:${ENVIRONMENT}
  - service:speedcam-ocr
  - team:backend
```

#### Alert Instance (Celery)

**datadog.yaml**
```yaml
api_key: ${DD_API_KEY}
site: datadoghq.com
hostname: speedcam-alert

apm_config:
  enabled: true
  apm_non_local_traffic: true

logs_enabled: true

tags:
  - env:${ENVIRONMENT}
  - service:speedcam-alert
  - team:backend
```

#### RabbitMQ Instance

**datadog.yaml**
```yaml
api_key: ${DD_API_KEY}
site: datadoghq.com
hostname: speedcam-rabbitmq

tags:
  - env:${ENVIRONMENT}
  - service:speedcam-rabbitmq
  - team:infra
```

**conf.d/rabbitmq.d/conf.yaml**
```yaml
# RabbitMQ Integration
init_config:

instances:
  - rabbitmq_api_url: http://localhost:15672/api/
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASS}
    tag_families: true
    queues:
      - ocr_queue
      - fcm_queue
      - dlq_queue
    exchanges:
      - ocr_exchange
      - fcm_exchange
      - dlq_exchange
```

### 7.3 Python 애플리케이션 설정

**core/datadog/tracer.py**
```python
import os
from ddtrace import config, patch_all, tracer

def configure_datadog():
    """DataDog 트레이싱 설정"""
    
    # 서비스 이름 설정
    config.service = os.getenv('DD_SERVICE', 'speedcam')
    config.env = os.getenv('DD_ENV', 'dev')
    
    # Django 설정
    config.django['service_name'] = config.service
    config.django['cache_service_name'] = f'{config.service}-cache'
    config.django['database_service_name'] = f'{config.service}-db'
    
    # Celery 설정
    config.celery['service_name'] = config.service
    config.celery['worker_service_name'] = f'{config.service}-worker'
    
    # 자동 패치
    patch_all(
        django=True,
        celery=True,
        mysql=True,
        requests=True,
        logging=True,
    )

# Django settings에서 호출
# config/settings/base.py
# from core.datadog.tracer import configure_datadog
# configure_datadog()
```

### 7.4 Docker Compose에 DataDog Agent 추가

```yaml
# docker-compose.yml (DataDog 섹션)
services:
  datadog-agent:
    image: gcr.io/datadoghq/agent:7
    environment:
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=datadoghq.com
      - DD_APM_ENABLED=true
      - DD_APM_NON_LOCAL_TRAFFIC=true
      - DD_LOGS_ENABLED=true
      - DD_LOGS_CONFIG_CONTAINER_COLLECT_ALL=true
      - DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /proc/:/host/proc/:ro
      - /sys/fs/cgroup/:/host/sys/fs/cgroup:ro
    ports:
      - "8126:8126"  # APM
      - "8125:8125/udp"  # DogStatsD
    networks:
      - speedcam-network
```

### 7.5 주요 모니터링 메트릭

| 서비스 | 메트릭 | 설명 |
|--------|--------|------|
| Django | `django.request.duration` | API 응답 시간 |
| Django | `django.request.count` | 요청 수 |
| Celery | `celery.task.runtime` | Task 실행 시간 |
| Celery | `celery.task.delay` | Task 대기 시간 |
| Celery | `celery.task.success` | 성공한 Task 수 |
| Celery | `celery.task.failure` | 실패한 Task 수 |
| RabbitMQ | `rabbitmq.queue.messages` | Queue 메시지 수 |
| RabbitMQ | `rabbitmq.queue.consumers` | Consumer 수 |

---

## 8. 데이터베이스 스키마

### 8.1 ER Diagram

```mermaid
erDiagram
    vehicles ||--o{ detections : has
    detections ||--o{ notifications : triggers
    
    vehicles {
        bigint id PK
        varchar plate_number UK "번호판"
        varchar owner_name "소유자명"
        varchar owner_phone "연락처"
        varchar fcm_token "FCM 토큰"
        datetime created_at
        datetime updated_at
    }
    
    detections {
        bigint id PK
        bigint vehicle_id FK
        float detected_speed "감지 속도"
        float speed_limit "제한 속도"
        varchar location "위치"
        varchar camera_id "카메라 ID"
        varchar image_gcs_uri "GCS 이미지 경로"
        varchar ocr_result "OCR 결과"
        float ocr_confidence "OCR 신뢰도"
        datetime detected_at "감지 시간"
        datetime processed_at "처리 완료 시간"
        enum status "pending|processing|completed|failed"
        text error_message "에러 메시지"
        datetime created_at
        datetime updated_at
    }
    
    notifications {
        bigint id PK
        bigint detection_id FK
        varchar fcm_token "FCM 토큰"
        varchar title "알림 제목"
        text body "알림 내용"
        datetime sent_at "전송 시간"
        enum status "pending|sent|failed"
        int retry_count "재시도 횟수"
        text error_message "에러 메시지"
        datetime created_at
    }
```

### 8.2 DDL

```sql
-- vehicles 테이블
CREATE TABLE vehicles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    plate_number VARCHAR(20) NOT NULL UNIQUE,
    owner_name VARCHAR(100),
    owner_phone VARCHAR(20),
    fcm_token VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_plate_number (plate_number),
    INDEX idx_fcm_token (fcm_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- detections 테이블
CREATE TABLE detections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id BIGINT,
    detected_speed FLOAT NOT NULL,
    speed_limit FLOAT NOT NULL,
    location VARCHAR(255),
    camera_id VARCHAR(50),
    image_gcs_uri VARCHAR(500) NOT NULL,
    ocr_result VARCHAR(20),
    ocr_confidence FLOAT,
    detected_at DATETIME NOT NULL,
    processed_at DATETIME,
    status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL,
    INDEX idx_vehicle_id (vehicle_id),
    INDEX idx_detected_at (detected_at),
    INDEX idx_status_created (status, created_at),
    INDEX idx_camera_detected (camera_id, detected_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- notifications 테이블
CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    detection_id BIGINT NOT NULL,
    fcm_token VARCHAR(255),
    title VARCHAR(255),
    body TEXT,
    sent_at DATETIME,
    status ENUM('pending', 'sent', 'failed') DEFAULT 'pending',
    retry_count INT DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE CASCADE,
    INDEX idx_detection_id (detection_id),
    INDEX idx_status_retry (status, retry_count),
    INDEX idx_sent_at (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 9. Celery 설정

### 9.1 config/celery.py

```python
import os
from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('speedcam')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['tasks'])

# Exchange 정의
ocr_exchange = Exchange('ocr_exchange', type='direct', durable=True)
fcm_exchange = Exchange('fcm_exchange', type='direct', durable=True)
dlq_exchange = Exchange('dlq_exchange', type='fanout', durable=True)

# Queue 정의
app.conf.task_queues = (
    Queue(
        'ocr_queue',
        exchange=ocr_exchange,
        routing_key='ocr',
        queue_arguments={
            'x-dead-letter-exchange': 'dlq_exchange',
            'x-message-ttl': 3600000,
            'x-max-priority': 10,
        }
    ),
    Queue(
        'fcm_queue',
        exchange=fcm_exchange,
        routing_key='fcm',
        queue_arguments={
            'x-dead-letter-exchange': 'dlq_exchange',
            'x-message-ttl': 3600000,
        }
    ),
    Queue(
        'dlq_queue',
        exchange=dlq_exchange,
        routing_key='',
    ),
)

# Task 라우팅
app.conf.task_routes = {
    'tasks.ocr_tasks.process_ocr': {
        'queue': 'ocr_queue',
        'exchange': 'ocr_exchange',
        'routing_key': 'ocr',
    },
    'tasks.notification_tasks.send_notification': {
        'queue': 'fcm_queue',
        'exchange': 'fcm_exchange',
        'routing_key': 'fcm',
    },
}

# 기본 설정
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Seoul',
    enable_utc=True,
    
    # 안정성 설정
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    
    # Timeout
    task_time_limit=300,
    task_soft_time_limit=240,
    
    # Worker prefetch
    worker_prefetch_multiplier=1,
)
```

### 9.2 config/settings/base.py (Celery 관련)

```python
import os

# Celery 브로커 URL (RabbitMQ)
CELERY_BROKER_URL = os.getenv(
    'CELERY_BROKER_URL', 
    'amqp://sa:1234@rabbitmq:5672//'
)

# Result Backend (필요한 경우만)
CELERY_RESULT_BACKEND = 'django-db'

# 직렬화
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# 시간대
CELERY_TIMEZONE = 'Asia/Seoul'
CELERY_ENABLE_UTC = True

# 안정성
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Timeout
CELERY_TASK_TIME_LIMIT = 300  # 5분
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4분

# Prefetch (Worker별 설정 권장)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
```

---

## 10. 서비스별 상세 설계

### 10.1 Main Service (Django)

#### MQTT Subscriber

```python
# core/mqtt/subscriber.py
import json
import os
import paho.mqtt.client as mqtt
from apps.detections.models import Detection
from tasks.ocr_tasks import process_ocr

class MQTTSubscriber:
    def __init__(self):
        self.client = mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # 인증 설정
        username = os.getenv('MQTT_USER', 'mqtt_user')
        password = os.getenv('MQTT_PASS', 'mqtt_pass')
        self.client.username_pw_set(username, password)
    
    def on_connect(self, client, userdata, flags, rc, properties=None):
        print(f"Connected to MQTT broker with code {rc}")
        client.subscribe("detections/new", qos=1)
    
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            
            # 1. pending 레코드 즉시 생성
            detection = Detection.objects.create(
                camera_id=payload['camera_id'],
                location=payload['location'],
                detected_speed=payload['detected_speed'],
                speed_limit=payload['speed_limit'],
                detected_at=payload['detected_at'],
                image_gcs_uri=payload['image_gcs_uri'],
                status='pending'
            )
            
            # 2. OCR Task 발행 (AMQP)
            process_ocr.apply_async(
                args=[detection.id],
                kwargs={'gcs_uri': payload['image_gcs_uri']},
                queue='ocr_queue',
                priority=5
            )
            
        except Exception as e:
            print(f"Error: {e}")
    
    def start(self):
        host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        port = int(os.getenv('MQTT_PORT', 1883))
        self.client.connect(host, port, 60)
        self.client.loop_forever()
```

### 10.2 OCR Service (Celery Worker)

```python
# tasks/ocr_tasks.py
import re
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from google.cloud import storage
import easyocr

from apps.detections.models import Detection
from apps.vehicles.models import Vehicle
from tasks.notification_tasks import send_notification

reader = easyocr.Reader(['ko', 'en'], gpu=False)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True
)
def process_ocr(self, detection_id: int, gcs_uri: str):
    try:
        # 1. 상태 업데이트
        Detection.objects.filter(id=detection_id).update(
            status='processing',
            updated_at=timezone.now()
        )
        
        # 2. GCS 이미지 다운로드
        storage_client = storage.Client()
        bucket_name = gcs_uri.split('/')[2]
        blob_path = '/'.join(gcs_uri.split('/')[3:])
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        image_bytes = blob.download_as_bytes()
        
        # 3. OCR 실행
        results = reader.readtext(image_bytes)
        
        # 4. 번호판 파싱
        plate_number, confidence = parse_plate(results)
        
        # 5. DB 직접 업데이트 (Choreography)
        with transaction.atomic():
            detection = Detection.objects.select_for_update().get(
                id=detection_id
            )
            detection.ocr_result = plate_number
            detection.ocr_confidence = confidence
            detection.status = 'completed'
            detection.processed_at = timezone.now()
            detection.save()
            
            # 6. Vehicle 매칭 & 알림 발행
            if plate_number:
                vehicle = Vehicle.objects.filter(
                    plate_number=plate_number
                ).first()
                
                if vehicle:
                    detection.vehicle_id = vehicle.id
                    detection.save(update_fields=['vehicle_id'])
                    
                    if vehicle.fcm_token:
                        send_notification.apply_async(
                            args=[detection_id],
                            queue='fcm_queue'
                        )
        
        return {
            'detection_id': detection_id,
            'plate': plate_number,
            'confidence': confidence
        }
        
    except Exception as exc:
        Detection.objects.filter(id=detection_id).update(
            status='failed',
            error_message=str(exc)
        )
        raise self.retry(exc=exc)


def parse_plate(results):
    """번호판 파싱"""
    pattern = r'^\d{2,3}[가-힣]\d{4}$'
    
    for bbox, text, conf in results:
        normalized = text.replace(' ', '')
        if re.match(pattern, normalized):
            return normalized, conf
    
    return None, 0.0
```

### 10.3 Alert Service (Celery Worker)

```python
# tasks/notification_tasks.py
from celery import shared_task
from django.utils import timezone
from firebase_admin import messaging
from firebase_admin.exceptions import FirebaseError

from apps.detections.models import Detection
from apps.notifications.models import Notification

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(FirebaseError,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True
)
def send_notification(self, detection_id: int):
    try:
        detection = Detection.objects.select_related('vehicle').get(
            id=detection_id,
            status='completed'
        )
        
        if not detection.vehicle or not detection.vehicle.fcm_token:
            return {'status': 'skipped', 'reason': 'No FCM token'}
        
        vehicle = detection.vehicle
        
        # FCM 메시지 생성
        title = f"⚠️ 과속 위반: {detection.ocr_result}"
        body = f"📍 {detection.location}\n🚗 {detection.detected_speed}km/h"
        
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={
                'detection_id': str(detection_id),
                'plate': detection.ocr_result or '',
                'speed': str(detection.detected_speed),
            },
            token=vehicle.fcm_token
        )
        
        # FCM 전송
        response = messaging.send(message)
        
        # 이력 저장
        Notification.objects.create(
            detection_id=detection_id,
            fcm_token=vehicle.fcm_token,
            title=title,
            body=body,
            status='sent',
            sent_at=timezone.now()
        )
        
        return {'status': 'sent', 'response': response}
        
    except FirebaseError as exc:
        Notification.objects.create(
            detection_id=detection_id,
            status='failed',
            retry_count=self.request.retries,
            error_message=str(exc)
        )
        raise
```

---

## 11. Docker Compose (로컬 개발)

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: speedcam-mysql
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: speedcam
      MYSQL_USER: sa
      MYSQL_PASSWORD: "1234"
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "sa", "-p1234"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - speedcam-network

  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: speedcam-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: sa
      RABBITMQ_DEFAULT_PASS: "1234"
    ports:
      - "5672:5672"    # AMQP
      - "1883:1883"    # MQTT
      - "15672:15672"  # Management UI
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
      - ./rabbitmq/enabled_plugins:/etc/rabbitmq/enabled_plugins
      - ./rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - speedcam-network

  main:
    build:
      context: .
      dockerfile: docker/Dockerfile.main
    container_name: speedcam-main
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - RABBITMQ_HOST=rabbitmq
      - MQTT_PORT=1883
      - MQTT_USER=sa
      - MQTT_PASS=1234
      - DD_AGENT_HOST=datadog-agent
      - DD_SERVICE=speedcam-main
      - DD_ENV=dev
    ports:
      - "8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - speedcam-network
    labels:
      com.datadoghq.ad.logs: '[{"source": "django", "service": "speedcam-main"}]'

  ocr-worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.ocr
    container_name: speedcam-ocr
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - OCR_CONCURRENCY=2
      - DD_AGENT_HOST=datadog-agent
      - DD_SERVICE=speedcam-ocr
      - DD_ENV=dev
    depends_on:
      - main
      - rabbitmq
    networks:
      - speedcam-network
    labels:
      com.datadoghq.ad.logs: '[{"source": "celery", "service": "speedcam-ocr"}]'

  alert-worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.alert
    container_name: speedcam-alert
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - ALERT_CONCURRENCY=50
      - DD_AGENT_HOST=datadog-agent
      - DD_SERVICE=speedcam-alert
      - DD_ENV=dev
    depends_on:
      - main
      - rabbitmq
    networks:
      - speedcam-network
    labels:
      com.datadoghq.ad.logs: '[{"source": "celery", "service": "speedcam-alert"}]'

  flower:
    build:
      context: .
      dockerfile: docker/Dockerfile.main
    container_name: speedcam-flower
    command: celery -A config flower --port=5555
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
    ports:
      - "5555:5555"
    depends_on:
      - rabbitmq
    networks:
      - speedcam-network

  datadog-agent:
    image: gcr.io/datadoghq/agent:7
    container_name: speedcam-datadog
    environment:
      - DD_API_KEY=${DD_API_KEY}
      - DD_SITE=datadoghq.com
      - DD_APM_ENABLED=true
      - DD_APM_NON_LOCAL_TRAFFIC=true
      - DD_LOGS_ENABLED=true
      - DD_LOGS_CONFIG_CONTAINER_COLLECT_ALL=true
      - DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /proc/:/host/proc/:ro
      - /sys/fs/cgroup/:/host/sys/fs/cgroup:ro
      - ./datadog/conf.d:/etc/datadog-agent/conf.d:ro
    ports:
      - "8126:8126"      # APM
      - "8125:8125/udp"  # DogStatsD
    networks:
      - speedcam-network

volumes:
  mysql_data:
  rabbitmq_data:

networks:
  speedcam-network:
    driver: bridge
```

### RabbitMQ 설정 파일

**rabbitmq/enabled_plugins**
```
[rabbitmq_management, rabbitmq_mqtt].
```

**rabbitmq/rabbitmq.conf**
```conf
# MQTT Plugin 설정
mqtt.listeners.tcp.default = 1883
mqtt.allow_anonymous = false
mqtt.default_user = sa
mqtt.default_pass = 1234
mqtt.vhost = /
mqtt.exchange = amq.topic
mqtt.subscription_ttl = 86400000
mqtt.prefetch = 10

# Management Plugin
management.tcp.port = 15672
```

---

## 12. 환경 변수

```env
# .env.example

# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_SETTINGS_MODULE=config.settings.dev
DEBUG=True

# Database (로컬: sa/1234, 운영: 별도 설정)
DB_HOST=mysql
DB_PORT=3306
DB_NAME=speedcam
DB_USER=sa
DB_PASSWORD=1234

# RabbitMQ (로컬: sa/1234, 운영: 별도 설정)
CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
RABBITMQ_HOST=rabbitmq
MQTT_PORT=1883
MQTT_USER=sa
MQTT_PASS=1234

# GCS
GCS_BUCKET_NAME=your-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Firebase
FIREBASE_CREDENTIALS=/path/to/firebase-service-account.json

# DataDog
DD_API_KEY=your-datadog-api-key
DD_SITE=datadoghq.com
DD_ENV=dev

# Worker Concurrency
OCR_CONCURRENCY=4
ALERT_CONCURRENCY=100
```

---

## 13. 핵심 설계 원칙

### 13.1 Choreography Pattern
- 각 서비스가 **자기 할 일만 하고 다음 이벤트를 발행**
- OCR Worker가 직접 MySQL 업데이트 (Main Service를 거치지 않음)
- 서비스 간 느슨한 결합 → 독립적 확장/배포 가능

### 13.2 데이터 손실 방지
- Main Service가 MQTT 메시지 수신 시 **즉시 pending 레코드 생성**
- OCR 실패해도 "무언가 감지되었다"는 사실 추적 가능
- DLQ로 실패한 Task 별도 관리

### 13.3 프로토콜 분리
- **MQTT**: IoT 디바이스(Raspberry Pi) 통신용 경량 프로토콜
- **AMQP**: 백엔드 서비스 간 안정적인 메시지 전달

### 13.4 GIL 병목 회피
- **OCR Worker**: `prefork` pool (multiprocessing) - CPU 집약적
- **Alert Worker**: `gevent` pool (I/O 멀티플렉싱) - I/O 집약적

### 13.5 독립 배포
- 각 서비스(Main, OCR, Alert)가 별도 인스턴스에 배포
- 공유 코드베이스 + 서비스별 Dockerfile/의존성
- RabbitMQ를 통한 서비스 간 통신
