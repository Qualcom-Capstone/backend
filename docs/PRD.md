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
- 각 서비스가 자율적으로 자신의 DB를 업데이트하고 다음 이벤트를 발행
- **서비스별 독립 데이터베이스** (Database per Service)

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
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           └──────────────────────┼──────────────────────┘                   │
│                                  │                                          │
│                     ┌────────────▼────────────┐                             │
│                     │   RabbitMQ Instance     │                             │
│                     │   (Message Broker)      │                             │
│                     │   - MQTT Plugin         │                             │
│                     │   - AMQP Queues         │                             │
│                     └────────────┬────────────┘                             │
│                                  │                                          │
│  ┌───────────────────────────────┼───────────────────────────────┐         │
│  │              Cloud SQL (MySQL) - Multi-Database                │         │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────┐  │         │
│  │  │ speedcam  │ │ vehicles  │ │detections │ │notifications  │  │         │
│  │  │ (default) │ │    _db    │ │    _db    │ │     _db       │  │         │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────┘  │         │
│  └───────────────────────────────────────────────────────────────┘         │
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
        end
        
        subgraph OCRInst["OCR Instance"]
            OCR[OCR Worker<br/>Celery prefork]
        end
        
        subgraph AlertInst["Alert Instance"]
            FCM[Notification Worker<br/>Celery gevent]
        end
        
        subgraph DBCluster["Cloud SQL Cluster"]
            MySQL_Default[(speedcam<br/>Django Core)]
            MySQL_Vehicles[(speedcam_vehicles<br/>Vehicles)]
            MySQL_Detections[(speedcam_detections<br/>Detections)]
            MySQL_Notifications[(speedcam_notifications<br/>Notifications)]
        end
    end
    
    subgraph External["External Services"]
        Firebase[Firebase FCM]
    end
    
    Pi -->|1. 이미지 업로드| GCS
    Pi -->|2. MQTT Publish| MQTT
    MQTT -->|3. MQTT Subscribe| Django
    Django -->|4. pending 레코드| MySQL_Detections
    Django -->|5. AMQP Publish| AMQP
    AMQP -->|ocr_queue| OCR
    OCR -->|6. 이미지 다운로드| GCS
    OCR -->|7. 결과 업데이트| MySQL_Detections
    OCR -->|7-1. 차량 조회| MySQL_Vehicles
    OCR -->|8. MQTT Publish<br/>detections/completed| MQTT
    MQTT -->|9. MQTT Subscribe| Django
    Django -->|10. AMQP Publish| AMQP
    AMQP -->|fcm_queue| FCM
    FCM -->|11. 차량/토큰 조회| MySQL_Vehicles
    FCM -->|12. 푸시 전송| Firebase
    FCM -->|13. 이력 저장| MySQL_Notifications
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
    participant VDB as vehicles_db
    participant DDB as detections_db
    participant NDB as notifications_db

    Note over Pi: 과속 차량 감지
    Pi->>GCS: 1. 이미지 업로드
    Pi->>MQTT: 2. MQTT Publish (detections/new)
    
    MQTT->>Django: 3. MQTT Subscribe
    Django->>DDB: 4. Detection 생성 (status=pending)
    Django->>AMQP: 5. Publish to ocr_exchange (Direct)
    
    AMQP->>OCR: 6. Consume from ocr_queue
    OCR->>GCS: 7. 이미지 다운로드
    OCR->>OCR: 8. EasyOCR 실행
    OCR->>DDB: 9. 직접 업데이트 (status=completed)
    OCR->>VDB: 10. 번호판으로 Vehicle 조회
    OCR->>DDB: 11. vehicle_id 매핑
    OCR->>MQTT: 12. MQTT Publish (detections/completed)

    MQTT->>Django: 13. MQTT Subscribe (detections/completed)
    Django->>AMQP: 14. Publish to fcm_exchange

    AMQP->>FCM: 15. Consume from fcm_queue
    FCM->>DDB: 16. Detection 조회
    FCM->>VDB: 17. Vehicle/FCM 토큰 조회
    FCM->>FCM: 18. FCM API 호출
    FCM->>NDB: 19. 알림 이력 저장
```

---

## 3. 기술 스택

### 3.1 Backend
| 구분 | 기술 | 버전 |
|------|------|------|
| Language | Python | 3.12+ |
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

### 3.4 Monitoring & Observability
| 구분 | 기술 | 용도 |
|------|------|------|
| Metrics | Prometheus + Grafana | 시스템/컨테이너 메트릭 수집 및 시각화 |
| Logging | Loki + Promtail | 중앙 집중식 로그 수집 및 검색 |
| Tracing | OpenTelemetry + Jaeger | 분산 트레이싱 (서비스 간 요청 추적) |
| Task Monitoring | Flower | Celery Task 모니터링 |
| Queue Dashboard | RabbitMQ Management | Queue 상태 확인 |
| Container Metrics | cAdvisor | 컨테이너 리소스 사용량 |

---

## 4. MSA 데이터베이스 설계

### 4.1 Database per Service Pattern

MSA 환경에서 각 서비스는 **독립적인 데이터베이스**를 사용하여 느슨한 결합을 유지합니다.

| 서비스 | 데이터베이스 | 용도 |
|--------|-------------|------|
| Django Core | `speedcam` | Auth, Admin, Sessions, Celery Results |
| Vehicles Service | `speedcam_vehicles` | 차량 정보, FCM 토큰 |
| Detections Service | `speedcam_detections` | 과속 감지 내역, OCR 결과 |
| Notifications Service | `speedcam_notifications` | 알림 전송 이력 |

### 4.2 Cross-Service Reference

MSA에서 서비스 간 데이터 참조는 **Foreign Key 대신 ID 참조**를 사용합니다:

```
┌─────────────────┐     ID Reference      ┌─────────────────┐
│   vehicles_db   │ ◄──────────────────── │  detections_db  │
│                 │    vehicle_id         │                 │
│   Vehicle       │                       │   Detection     │
│   - id (PK)     │                       │   - id (PK)     │
│   - plate_number│                       │   - vehicle_id  │
│   - fcm_token   │                       │   - status      │
└─────────────────┘                       └─────────────────┘
                                                   │
                                          ID Reference
                                          detection_id
                                                   │
                                          ┌────────▼────────┐
                                          │notifications_db │
                                          │                 │
                                          │   Notification  │
                                          │   - id (PK)     │
                                          │   - detection_id│
                                          │   - status      │
                                          └─────────────────┘
```

### 4.3 Database Router

Django의 Database Router를 사용하여 자동으로 적절한 데이터베이스로 라우팅합니다:

```python
# config/db_router.py
class AppRouter:
    """서비스별 데이터베이스 라우팅"""
    
    route_app_labels = {
        'vehicles': 'vehicles_db',
        'detections': 'detections_db',
        'notifications': 'notifications_db',
    }
    
    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return self.route_app_labels[model._meta.app_label]
        return 'default'
    
    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return self.route_app_labels[model._meta.app_label]
        return 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        # MSA: 다른 DB 간 FK 관계 불허
        return False
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            return db == self.route_app_labels[app_label]
        return db == 'default'
```

### 4.4 ER Diagram (Updated)

```mermaid
erDiagram
    %% vehicles_db
    vehicles {
        bigint id PK
        varchar plate_number UK "번호판"
        varchar owner_name "소유자명"
        varchar owner_phone "연락처"
        varchar fcm_token "FCM 토큰"
        datetime created_at
        datetime updated_at
    }
    
    %% detections_db
    detections {
        bigint id PK
        bigint vehicle_id "차량 ID (Reference)"
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
    
    %% notifications_db
    notifications {
        bigint id PK
        bigint detection_id "감지 ID (Reference)"
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

### 4.5 DDL (Updated for MSA)

```sql
-- =============================================
-- Database: speedcam_vehicles
-- =============================================
CREATE DATABASE IF NOT EXISTS speedcam_vehicles;
USE speedcam_vehicles;

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

-- =============================================
-- Database: speedcam_detections
-- =============================================
CREATE DATABASE IF NOT EXISTS speedcam_detections;
USE speedcam_detections;

CREATE TABLE detections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id BIGINT,  -- ID Reference (No FK)
    detected_speed FLOAT NOT NULL,
    speed_limit FLOAT NOT NULL DEFAULT 60.0,
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
    INDEX idx_vehicle_id (vehicle_id),
    INDEX idx_detected_at (detected_at),
    INDEX idx_status_created (status, created_at),
    INDEX idx_camera_detected (camera_id, detected_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- Database: speedcam_notifications
-- =============================================
CREATE DATABASE IF NOT EXISTS speedcam_notifications;
USE speedcam_notifications;

CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    detection_id BIGINT NOT NULL,  -- ID Reference (No FK)
    fcm_token VARCHAR(255),
    title VARCHAR(255),
    body TEXT,
    sent_at DATETIME,
    status ENUM('pending', 'sent', 'failed') DEFAULT 'pending',
    retry_count INT DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_detection_id (detection_id),
    INDEX idx_status_retry (status, retry_count),
    INDEX idx_sent_at (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 5. RabbitMQ 메시징 설계

### 5.1 프로토콜 활용 전략

```mermaid
graph LR
    subgraph MQTT["MQTT (Port 1883)"]
        direction TB
        M1[Raspberry Pi] -->|Publish| M2[detections/new]
        M2 -->|Subscribe| M3[Django]
        M4[OCR Worker] -->|Publish| M5[detections/completed]
        M5 -->|Subscribe| M3
    end

    subgraph AMQP["AMQP (Port 5672)"]
        direction TB
        A1[Django] -->|Publish| A2[ocr_exchange]
        A2 -->|Route| A3[ocr_queue]
        A3 -->|Consume| A4[OCR Worker]

        A1 -->|Publish| A5[fcm_exchange]
        A5 -->|Route| A6[fcm_queue]
        A6 -->|Consume| A7[Alert Worker]
    end
```

| 프로토콜 | 용도 | 특징 |
|----------|------|------|
| **MQTT** | IoT → Django, OCR → Django (도메인 이벤트) | 경량 프로토콜, QoS 1, Choreography 이벤트 전파 |
| **AMQP** | Django → Celery Workers (Task 분배) | 안정적인 메시지 전달, Exchange/Queue 라우팅 |

### 5.2 Exchange 설계

| Exchange | Type | Routing Key | 용도 |
|----------|------|-------------|------|
| `ocr_exchange` | **Direct** | `ocr` | OCR Task 라우팅 |
| `fcm_exchange` | **Direct** | `fcm` | 알림 Task 라우팅 |
| `dlq_exchange` | **Fanout** | - | Dead Letter 처리 |

**Direct Exchange 선택 이유:**
- 1:1 라우팅으로 명확한 Task 분배
- Routing Key 기반 정확한 Queue 매핑
- Topic Exchange보다 단순하고 오버헤드 적음

### 5.3 Queue 설계

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

### 5.4 Queue 설정 상세

| Queue | Durable | TTL | Max Priority | DLQ | Prefetch |
|-------|---------|-----|--------------|-----|----------|
| `ocr_queue` | ✅ | 1시간 | 10 | ✅ | 1 |
| `fcm_queue` | ✅ | 1시간 | - | ✅ | 10 |
| `dlq_queue` | ✅ | - | - | - | 1 |

**Prefetch 설정 이유:**
- `ocr_queue`: 1 (CPU 집약적, 한 번에 하나씩 처리)
- `fcm_queue`: 10 (I/O 대기 시간 활용)

### 5.5 메시지 흐름

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
    │ Detection 생성 (detections_db)
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
    │ Detection 업데이트 (detections_db)
    │ Vehicle 조회 (vehicles_db)
    │
    │ MQTT Publish (Choreography)
    │ Topic: detections/completed
    │ QoS: 1
    ▼
[RabbitMQ MQTT Plugin]
    │
    │ MQTT Subscribe
    ▼
[Django MQTT Subscriber]
    │
    │ 이벤트 수신 & 라우팅
    │
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
    │ Detection 조회 (detections_db)
    │ Vehicle 조회 (vehicles_db)
    │ FCM 전송 완료
    │ Notification 저장 (notifications_db)
    ▼
[End]
```

---

## 6. Trade-off 분석

### 6.1 Choreography vs Orchestration

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

### 6.2 RabbitMQ vs Google Cloud Pub/Sub

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

### 6.3 prefork vs gevent Pool

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

```bash
# OCR Worker 실행
celery -A config worker --pool=prefork --concurrency=4 --queues=ocr_queue

# Alert Worker 실행
celery -A config worker --pool=gevent --concurrency=100 --queues=fcm_queue
```

### 6.4 Single DB vs Database per Service

| 항목 | Single DB | Database per Service (선택) |
|------|-----------|----------------------------|
| **결합도** | 높음 (스키마 공유) | 낮음 ✅ |
| **독립 배포** | 어려움 | 가능 ✅ |
| **데이터 일관성** | 트랜잭션 보장 | 최종 일관성 |
| **조인 쿼리** | 가능 | 불가 (Application Join) |
| **스키마 변경** | 전체 영향 | 서비스별 독립 ✅ |
| **복잡도** | 단순 | 서비스 간 데이터 조회 복잡 |

**선택 이유:**
- MSA 원칙 준수: 서비스 간 느슨한 결합
- 독립 배포 및 확장 가능
- 한 서비스의 DB 장애가 다른 서비스에 영향 최소화

---

## 7. 프로젝트 구조 (분리 배포용)

### 7.1 Monorepo 구조

각 서비스는 **동일한 코드베이스**를 공유하되, 실행 시 역할에 따라 다른 컴포넌트만 활성화합니다.

```
backend/
├── docker/
│   ├── Dockerfile.main          # Main Service (Django)
│   ├── Dockerfile.ocr           # OCR Service (Celery)
│   ├── Dockerfile.alert         # Alert Service (Celery)
│   ├── docker-compose.yml       # 로컬 개발용
│   ├── mysql/
│   │   └── init.sql             # Multi-DB 초기화 스크립트
│   └── rabbitmq/
│       └── enabled_plugins      # MQTT 플러그인 활성화
│
├── config/
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py              # 공통 설정
│   │   ├── dev.py               # 개발 환경 (Multi-DB)
│   │   └── prod.py              # 운영 환경
│   ├── db_router.py             # MSA Database Router
│   ├── celery.py                # Celery 설정
│   ├── urls.py
│   └── wsgi.py
│
├── apps/                        # Django Apps (서비스별 독립 DB)
│   ├── __init__.py
│   ├── vehicles/                # → vehicles_db
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── admin.py
│   ├── detections/              # → detections_db
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── admin.py
│   └── notifications/           # → notifications_db
│       ├── __init__.py
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       └── admin.py
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
│   │   ├── publisher.py         # 도메인 이벤트 발행 (Choreography)
│   │   └── subscriber.py        # 도메인 이벤트 수신 및 라우팅
│   ├── gcs/
│   │   ├── __init__.py
│   │   └── client.py            # GCS 클라이언트
│   └── firebase/
│       ├── __init__.py
│       └── fcm.py               # FCM 클라이언트
│
├── scripts/
│   ├── start_main.sh            # Main Service 시작
│   ├── start_ocr_worker.sh      # OCR Worker 시작
│   └── start_alert_worker.sh    # Alert Worker 시작
│
├── tests/                       # 테스트 코드
│   ├── __init__.py
│   ├── conftest.py              # Pytest 설정
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_serializers.py
│   │   └── test_tasks.py
│   └── integration/
│       ├── test_api_endpoints.py
│       └── test_event_flow.py
│
├── credentials/                 # 인증 정보 (Git 제외)
│   └── .gitkeep
│
├── manage.py
├── pytest.ini
├── requirements/
│   ├── base.txt                 # 공통 의존성
│   ├── main.txt                 # Main Service 의존성
│   ├── ocr.txt                  # OCR Service 의존성
│   ├── alert.txt                # Alert Service 의존성
│   └── test.txt                 # 테스트 의존성
│
└── backend.env.example
```

### 7.2 서비스별 의존성

**requirements/base.txt** (공통)
```txt
Django==5.1.7
djangorestframework==3.15.2
django-filter==24.3
django-cors-headers==4.7.0
celery==5.5.2
django-celery-results==2.5.1
PyMySQL==1.1.1
python-dotenv==1.0.1
```

**requirements/main.txt** (Main Service)
```txt
-r base.txt
gunicorn==23.0.0
paho-mqtt==2.0.0
drf-yasg==1.21.10
flower==2.0.0
```

**requirements/ocr.txt** (OCR Service)
```txt
-r base.txt
easyocr==1.7.2
opencv-python-headless==4.10.0.84
pillow==11.2.1
google-cloud-storage==2.18.2
paho-mqtt==2.1.0
```

**requirements/alert.txt** (Alert Service)
```txt
-r base.txt
firebase-admin==6.8.0
gevent==24.2.1
```

### 7.3 서비스별 Dockerfile

**docker/Dockerfile.main**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements/base.txt requirements/main.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/main.txt

# 앱 복사
COPY . .

# 스크립트 권한
RUN chmod +x scripts/*.sh

EXPOSE 8000

CMD ["sh", "scripts/start_main.sh"]
```

**docker/Dockerfile.ocr**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (OpenCV)
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements/base.txt requirements/ocr.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/ocr.txt

# 앱 복사
COPY . .

# 스크립트 권한
RUN chmod +x scripts/*.sh

CMD ["sh", "scripts/start_ocr_worker.sh"]
```

**docker/Dockerfile.alert**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements/base.txt requirements/alert.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/alert.txt

# 앱 복사
COPY . .

# 스크립트 권한
RUN chmod +x scripts/*.sh

CMD ["sh", "scripts/start_alert_worker.sh"]
```

### 7.4 서비스 시작 스크립트

**scripts/start_main.sh**
```bash
#!/bin/bash
set -e

echo "Starting Main Service (Django)..."

# Django 마이그레이션 (모든 DB)
echo "Running migrations for all databases..."
python manage.py migrate --noinput --database=default
python manage.py migrate --noinput --database=vehicles_db
python manage.py migrate --noinput --database=detections_db
python manage.py migrate --noinput --database=notifications_db

# Static 파일 수집 (프로덕션)
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.prod" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# MQTT Subscriber 백그라운드 실행
echo "Starting MQTT Subscriber..."
python -c "
import django
django.setup()
from core.mqtt.subscriber import start_mqtt_subscriber
start_mqtt_subscriber()
" &

# Gunicorn 시작
echo "Starting Gunicorn..."
gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-4} \
    --threads ${GUNICORN_THREADS:-2} \
    --access-logfile - \
    --error-logfile -
```

**scripts/start_ocr_worker.sh**
```bash
#!/bin/bash
set -e

echo "Starting OCR Worker (Celery)..."

# Celery Worker 시작 (prefork pool - CPU 집약적)
celery -A config worker \
    --pool=prefork \
    --concurrency=${OCR_CONCURRENCY:-4} \
    --queues=ocr_queue \
    --hostname=ocr@%h \
    --loglevel=${LOG_LEVEL:-info}
```

**scripts/start_alert_worker.sh**
```bash
#!/bin/bash
set -e

echo "Starting Alert Worker (Celery)..."

# Celery Worker 시작 (gevent pool - I/O 집약적)
celery -A config worker \
    --pool=gevent \
    --concurrency=${ALERT_CONCURRENCY:-100} \
    --queues=fcm_queue \
    --hostname=alert@%h \
    --loglevel=${LOG_LEVEL:-info}
```

---

## 8. Celery 설정

### 8.1 config/celery.py

```python
import os
from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('speedcam')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Exchange 정의
ocr_exchange = Exchange('ocr_exchange', type='direct', durable=True)
fcm_exchange = Exchange('fcm_exchange', type='direct', durable=True)
dlq_exchange = Exchange('dlq_exchange', type='fanout', durable=True)

# Celery 설정
app.conf.update(
    # Broker
    broker_connection_retry_on_startup=True,
    
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='Asia/Seoul',
    enable_utc=True,
    
    # Stability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Timeout
    task_time_limit=300,
    task_soft_time_limit=240,
    
    # Prefetch
    worker_prefetch_multiplier=1,
)

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

# Task 자동 발견
app.autodiscover_tasks(['tasks'])
```

---

## 9. 서비스별 상세 설계

### 9.1 Main Service (Django)

#### MQTT Subscriber

```python
# core/mqtt/subscriber.py
import json
import os
import logging
import paho.mqtt.client as mqtt
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

class MQTTSubscriber:
    """
    RabbitMQ MQTT Plugin을 통해 도메인 이벤트를 수신하는 Subscriber

    Choreography 패턴: 각 서비스는 이벤트를 발행하고,
    관심 있는 서비스가 독립적으로 구독하여 처리한다.

    구독 토픽:
    - detections/new      : IoT 디바이스 → Detection 생성 → OCR 발행
    - detections/completed : OCR 완료 이벤트 → Notification 발행
    """

    def __init__(self):
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
            client_id=f"django-main-{os.getpid()}"
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        username = os.getenv('MQTT_USER', '')
        password = os.getenv('MQTT_PASS', '')
        self.client.username_pw_set(username, password)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.error(f"MQTT connection failed: {reason_code}")
        else:
            logger.info("Connected to MQTT broker")
            client.subscribe("detections/new", qos=1)
            client.subscribe("detections/completed", qos=1)

    def on_message(self, client, userdata, msg):
        """토픽별 메시지 라우팅"""
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MQTT message: {e}")
            return

        if msg.topic == "detections/new":
            self._handle_new_detection(payload)
        elif msg.topic == "detections/completed":
            self._handle_detection_completed(payload)
        else:
            logger.warning(f"Unknown MQTT topic: {msg.topic}")

    def _handle_new_detection(self, payload):
        """detections/new → Detection 생성 → OCR Task 발행"""
        from apps.detections.models import Detection
        from tasks.ocr_tasks import process_ocr

        detection = Detection.objects.using('detections_db').create(
            camera_id=payload.get('camera_id'),
            location=payload.get('location'),
            detected_speed=payload['detected_speed'],
            speed_limit=payload.get('speed_limit', 60.0),
            detected_at=payload.get('detected_at', timezone.now()),
            image_gcs_uri=payload['image_gcs_uri'],
            status='pending'
        )

        process_ocr.apply_async(
            args=[detection.id],
            kwargs={'gcs_uri': payload['image_gcs_uri']},
            queue='ocr_queue',
            priority=5
        )

    def _handle_detection_completed(self, payload):
        """detections/completed → Notification Task 발행 (Choreography)"""
        detection_id = payload["detection_id"]

        from tasks.notification_tasks import send_notification
        send_notification.apply_async(
            args=[detection_id], queue="fcm_queue"
        )

    def start(self):
        host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        port = int(os.getenv('MQTT_PORT', 1883))
        self.client.connect(host, port, 60)
        self.client.loop_forever()
```

```python
# core/mqtt/publisher.py
"""도메인 이벤트 발행"""
import json
import logging
import os
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

def publish_event(topic: str, payload: dict):
    """Choreography 패턴에서 서비스 간 이벤트 전파"""
    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = int(os.getenv("MQTT_PORT", 1883))

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv311,
        client_id="",
    )
    client.username_pw_set(
        os.getenv("MQTT_USER", ""),
        os.getenv("MQTT_PASS", "")
    )

    try:
        client.connect(host, port, keepalive=10)
        client.loop_start()
        result = client.publish(topic, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=5)
    finally:
        client.loop_stop()
        client.disconnect()
```

### 9.2 OCR Service (Celery Worker)

```python
# tasks/ocr_tasks.py
import os
import re
import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Mock 모드 설정
OCR_MOCK = os.getenv('OCR_MOCK', 'false').lower() == 'true'

def mock_ocr_result():
    """Mock OCR 결과 생성"""
    import random
    plates = ["12가3456", "34나5678", "56다7890", "78라9012", "90마1234"]
    return random.choice(plates), round(random.uniform(0.85, 0.99), 2)

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True
)
def process_ocr(self, detection_id: int, gcs_uri: str):
    from apps.detections.models import Detection
    from apps.vehicles.models import Vehicle

    logger.info(f"Processing OCR for detection {detection_id}")
    
    try:
        # 1. 상태를 processing으로 업데이트 (detections_db)
        Detection.objects.using('detections_db').filter(id=detection_id).update(
            status='processing',
            updated_at=timezone.now()
        )
        
        if OCR_MOCK:
            # Mock 모드
            plate_number, confidence = mock_ocr_result()
            logger.info(f"Mock OCR result: {plate_number} ({confidence})")
        else:
            # 실제 OCR 처리
            from google.cloud import storage
            import easyocr
            
            # 2. GCS 이미지 다운로드
            storage_client = storage.Client()
            bucket_name = gcs_uri.split('/')[2]
            blob_path = '/'.join(gcs_uri.split('/')[3:])
            
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            image_bytes = blob.download_as_bytes()
            
            # 3. OCR 실행
            reader = easyocr.Reader(['ko', 'en'], gpu=False)
            results = reader.readtext(image_bytes)
            
            # 4. 번호판 파싱
            plate_number, confidence = parse_plate(results)
        
        # 5. 직접 MySQL 업데이트 (detections_db)
        with transaction.atomic(using='detections_db'):
            detection = Detection.objects.using('detections_db').select_for_update().get(id=detection_id)
            detection.ocr_result = plate_number
            detection.ocr_confidence = confidence
            detection.status = 'completed'
            detection.processed_at = timezone.now()
            detection.save(update_fields=[
                'ocr_result', 'ocr_confidence', 'status',
                'processed_at', 'updated_at'
            ])
            
            # 6. Vehicle 매칭 (vehicles_db)
            if plate_number:
                vehicle = Vehicle.objects.using('vehicles_db').filter(
                    plate_number=plate_number
                ).first()
                
                if vehicle:
                    detection.vehicle_id = vehicle.id
                    detection.save(update_fields=['vehicle_id', 'updated_at'])

        # 7. detection.completed 이벤트 발행 (Choreography)
        #    OCR은 알림의 존재를 모른다. 이벤트만 발행하고 끝.
        try:
            from core.mqtt.publisher import publish_event
            publish_event(
                "detections/completed",
                {"detection_id": detection_id},
            )
        except Exception as e:
            logger.warning(f"Failed to publish completion event: {e}")

        logger.info(f"OCR completed for detection {detection_id}: {plate_number}")
        return {
            'detection_id': detection_id,
            'plate': plate_number,
            'confidence': confidence
        }
        
    except Exception as exc:
        # 실패 시 에러 기록 (detections_db)
        Detection.objects.using('detections_db').filter(id=detection_id).update(
            status='failed',
            error_message=str(exc),
            updated_at=timezone.now()
        )
        logger.error(f"OCR failed for detection {detection_id}: {exc}")
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

### 9.3 Alert Service (Celery Worker)

```python
# tasks/notification_tasks.py
import os
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Mock 모드 설정
FCM_MOCK = os.getenv('FCM_MOCK', 'false').lower() == 'true'

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True
)
def send_notification(self, detection_id: int):
    from apps.detections.models import Detection
    from apps.vehicles.models import Vehicle
    from apps.notifications.models import Notification
    
    logger.info(f"Sending notification for detection {detection_id}")
    
    try:
        # 1. Detection 조회 (detections_db)
        try:
            detection = Detection.objects.using('detections_db').get(
                id=detection_id,
                status='completed'
            )
        except Detection.DoesNotExist:
            logger.error(f"Detection {detection_id} not found")
            return {'status': 'error', 'reason': 'Detection not found'}
        
        # 2. Vehicle 조회 (vehicles_db)
        vehicle = None
        if detection.vehicle_id:
            try:
                vehicle = Vehicle.objects.using('vehicles_db').get(id=detection.vehicle_id)
            except Vehicle.DoesNotExist:
                logger.warning(f"Vehicle {detection.vehicle_id} not found")
        
        if not vehicle or not vehicle.fcm_token:
            logger.warning(f"No FCM token for detection {detection_id}")
            return {'status': 'skipped', 'reason': 'No FCM token'}
        
        # 3. FCM 메시지 생성
        title = f"⚠️ 과속 위반 감지: {detection.ocr_result}"
        body = f"📍 위치: {detection.location or 'Unknown'}\n🚗 속도: {detection.detected_speed}km/h (제한: {detection.speed_limit}km/h)"
        
        if FCM_MOCK:
            # Mock 모드
            response = f"mock-message-id-{detection_id}"
            logger.info(f"Mock FCM sent: {title}")
        else:
            # 실제 FCM 전송
            import firebase_admin
            from firebase_admin import messaging
            
            if not firebase_admin._apps:
                cred_path = os.getenv('FIREBASE_CREDENTIALS')
                if cred_path:
                    cred = firebase_admin.credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
            
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={
                    'detection_id': str(detection_id),
                    'plate': detection.ocr_result or '',
                    'speed': str(detection.detected_speed),
                },
                token=vehicle.fcm_token
            )
            
            response = messaging.send(message)
        
        # 4. 성공 이력 저장 (notifications_db)
        Notification.objects.using('notifications_db').create(
            detection_id=detection_id,
            fcm_token=vehicle.fcm_token,
            title=title,
            body=body,
            status='sent',
            sent_at=timezone.now()
        )
        
        logger.info(f"Notification sent for detection {detection_id}: {response}")
        return {'status': 'sent', 'fcm_response': response}
        
    except Exception as exc:
        # FCM 실패 시 이력 저장 후 재시도 (notifications_db)
        try:
            Notification.objects.using('notifications_db').create(
                detection_id=detection_id,
                status='failed',
                retry_count=self.request.retries,
                error_message=str(exc)
            )
        except Exception:
            pass
        
        logger.error(f"Notification failed for detection {detection_id}: {exc}")
        raise
```

---

## 10. Docker Compose (로컬 개발)

```yaml
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
      - ./docker/mysql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
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
      RABBITMQ_MQTT_LISTENERS_TCP_DEFAULT: 1883
      RABBITMQ_MQTT_ALLOW_ANONYMOUS: "false"
      RABBITMQ_MQTT_DEFAULT_USER: sa
      RABBITMQ_MQTT_DEFAULT_PASS: "1234"
      RABBITMQ_MQTT_VHOST: /
      RABBITMQ_MQTT_EXCHANGE: amq.topic
    ports:
      - "5672:5672"    # AMQP
      - "1883:1883"    # MQTT
      - "15672:15672"  # Management UI
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
      - ./rabbitmq/enabled_plugins:/etc/rabbitmq/enabled_plugins
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - speedcam-network

  main:
    build:
      context: ..
      dockerfile: docker/Dockerfile.main
    container_name: speedcam-main
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_NAME_VEHICLES=speedcam_vehicles
      - DB_NAME_DETECTIONS=speedcam_detections
      - DB_NAME_NOTIFICATIONS=speedcam_notifications
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - RABBITMQ_HOST=rabbitmq
      - MQTT_PORT=1883
      - MQTT_USER=sa
      - MQTT_PASS=1234
      - OCR_MOCK=true
      - FCM_MOCK=true
    ports:
      - "8000:8000"
    volumes:
      - ../credentials:/app/credentials:ro
    depends_on:
      mysql:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - speedcam-network

  ocr-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.ocr
    container_name: speedcam-ocr
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_NAME_VEHICLES=speedcam_vehicles
      - DB_NAME_DETECTIONS=speedcam_detections
      - DB_NAME_NOTIFICATIONS=speedcam_notifications
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - OCR_CONCURRENCY=2
      - OCR_MOCK=true
    volumes:
      - ../credentials:/app/credentials:ro
    depends_on:
      - main
      - rabbitmq
    networks:
      - speedcam-network

  alert-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.alert
    container_name: speedcam-alert
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_PORT=3306
      - DB_NAME=speedcam
      - DB_NAME_VEHICLES=speedcam_vehicles
      - DB_NAME_DETECTIONS=speedcam_detections
      - DB_NAME_NOTIFICATIONS=speedcam_notifications
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - ALERT_CONCURRENCY=50
      - FCM_MOCK=true
    volumes:
      - ../credentials:/app/credentials:ro
    depends_on:
      - main
      - rabbitmq
    networks:
      - speedcam-network

  flower:
    build:
      context: ..
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

volumes:
  mysql_data:
  rabbitmq_data:

networks:
  speedcam-network:
    driver: bridge
```

### MySQL 초기화 스크립트

**docker/mysql/init.sql**
```sql
-- MSA용 데이터베이스 생성
CREATE DATABASE IF NOT EXISTS speedcam_vehicles;
CREATE DATABASE IF NOT EXISTS speedcam_detections;
CREATE DATABASE IF NOT EXISTS speedcam_notifications;

-- 사용자 권한 부여
GRANT ALL PRIVILEGES ON speedcam_vehicles.* TO 'sa'@'%';
GRANT ALL PRIVILEGES ON speedcam_detections.* TO 'sa'@'%';
GRANT ALL PRIVILEGES ON speedcam_notifications.* TO 'sa'@'%';

FLUSH PRIVILEGES;
```

### RabbitMQ 설정 파일

**rabbitmq/enabled_plugins**
```
[rabbitmq_management, rabbitmq_mqtt].
```

---

## 11. 환경 변수

```env
# backend.env.example

# ===========================================
# Django 설정
# ===========================================
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_SETTINGS_MODULE=config.settings.dev
DEBUG=True

# ===========================================
# 데이터베이스 설정 (MySQL - MSA Multi-DB)
# ===========================================
DB_HOST=mysql
DB_PORT=3306
DB_USER=sa
DB_PASSWORD=1234

# 서비스별 데이터베이스
DB_NAME=speedcam
DB_NAME_VEHICLES=speedcam_vehicles
DB_NAME_DETECTIONS=speedcam_detections
DB_NAME_NOTIFICATIONS=speedcam_notifications

# ===========================================
# RabbitMQ / Celery 설정
# ===========================================
CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
RABBITMQ_HOST=rabbitmq

# ===========================================
# MQTT 설정 (RabbitMQ MQTT Plugin)
# ===========================================
MQTT_PORT=1883
MQTT_USER=sa
MQTT_PASS=1234

# ===========================================
# GCS (Google Cloud Storage) 설정
# ===========================================
GCS_BUCKET_NAME=your-gcs-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcp-cloud-storage.json

# ===========================================
# Firebase 설정 (FCM Push Notification)
# ===========================================
FIREBASE_CREDENTIALS=/app/credentials/firebase-service-account.json

# ===========================================
# Celery Worker 설정
# ===========================================
OCR_CONCURRENCY=2
OCR_MOCK=true

ALERT_CONCURRENCY=50
FCM_MOCK=true

# ===========================================
# Gunicorn 설정
# ===========================================
GUNICORN_WORKERS=4
GUNICORN_THREADS=2

# ===========================================
# 로깅 설정
# ===========================================
LOG_LEVEL=info

# ===========================================
# CORS 설정
# ===========================================
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 12. 핵심 설계 원칙

### 12.1 Choreography Pattern
- 각 서비스가 **자기 할 일만 하고 다음 이벤트를 발행**
- OCR Worker가 직접 MySQL 업데이트 (Main Service를 거치지 않음)
- 서비스 간 느슨한 결합 → 독립적 확장/배포 가능

### 12.2 Database per Service
- 각 서비스는 **자신만의 데이터베이스** 사용
- ForeignKey 대신 **ID Reference**로 서비스 간 데이터 참조
- 한 서비스의 DB 장애가 다른 서비스에 영향 최소화

### 12.3 데이터 손실 방지
- Main Service가 MQTT 메시지 수신 시 **즉시 pending 레코드 생성**
- OCR 실패해도 "무언가 감지되었다"는 사실 추적 가능
- DLQ로 실패한 Task 별도 관리

### 12.4 프로토콜 분리
- **MQTT**: 도메인 이벤트 전파 (IoT→Main, OCR→Main) — Choreography 패턴의 이벤트 버스
- **AMQP**: Task 분배 (Main→Workers) — Celery를 통한 안정적인 작업 큐잉

### 12.5 GIL 병목 회피
- **OCR Worker**: `prefork` pool (multiprocessing) - CPU 집약적
- **Alert Worker**: `gevent` pool (I/O 멀티플렉싱) - I/O 집약적

### 12.6 독립 배포
- 각 서비스(Main, OCR, Alert)가 별도 인스턴스에 배포
- 공유 코드베이스 + 서비스별 Dockerfile/의존성
- RabbitMQ를 통한 서비스 간 통신

---

## 13. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0 | 2024-01 | 초기 PRD 작성 |
| 2.0 | 2026-01 | MSA Database 분리 아키텍처 적용 |
|     |         | - Database per Service 패턴 도입 |
|     |         | - ForeignKey → ID Reference 변경 |
|     |         | - Database Router 구현 |
|     |         | - Python 3.12로 버전 업데이트 |
|     |         | - DataDog 관련 설정 제거 (Optional) |
|     |         | - Mock 모드 추가 (OCR_MOCK, FCM_MOCK) |
| 3.0 | 2026-02 | Choreography 패턴 구현 반영 |
|     |         | - OCR → Alert 직접 호출 제거 (Orchestration → Choreography) |
|     |         | - MQTT Event Publisher 추가 (detections/completed) |
|     |         | - Subscriber 토픽 라우팅 구현 |
|     |         | - Monitoring 스택 반영 (Prometheus, Grafana, Loki, Jaeger) |
|     |         | - OCR Service에 paho-mqtt 의존성 추가 |
