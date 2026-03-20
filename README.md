# 과속 차량 감지 및 알림 시스템 — Backend

| 항목 | 내용 |
|------|------|
| **Authors** | 이상훈 (Backend Lead / DevOps) |
| **Status** | Living Document |
| **Last Updated** | 2026-03-21 |
| **Repository Scope** | Django API, Celery Worker 소스코드, Dockerfile, 로컬 개발 환경 |

Qualcomm 기반 Rubik Pi 엣지 디바이스에서 과속 차량을 감지하고 MQTT로 전송된 이벤트를 수신하여, EasyOCR로 번호판을 인식한 뒤 차량 소유자에게 Firebase Cloud Messaging 푸시 알림을 전송하는 백엔드 시스템이다. 엣지 디바이스(Rubik Pi)와 프론트엔드(React)는 범위에 포함하지 않는다.

### 저장소 책임 범위

| 항목 | 이 저장소 (backend) | deploy 저장소 |
|------|:---:|:---:|
| 애플리케이션 소스코드 | O | X |
| Dockerfile (3개) | O | X |
| 로컬 개발 docker-compose | O | X |
| GitHub Actions CI | O | X |
| 프로덕션 compose / 배포 | X | O |
| 프로덕션 모니터링 설정 | X | O |

---

## 아키텍처 개요

### 인스턴스 배포 구조

6개의 GCE 인스턴스로 구성되며, 모두 `asia-northeast3-a` 리전에 배치된다.

```
┌──────────────────────────────────────────────────────────────────────┐
│                       GCP (asia-northeast3-a)                        │
├───────────┬───────────┬───────────┬───────────┬───────────┬─────────┤
│  app      │  db       │  mq       │  ocr      │  alert    │  mon    │
│           │           │           │           │           │         │
│  Django   │  MySQL 8  │  RabbitMQ │  Celery   │  Kombu    │  Prome- │
│  Gunicorn │  4 DBs    │  MQTT     │  prefork  │  Consumer │  theus  │
│  MQTT Sub │           │  AMQP     │           │  + Celery │  Grafana│
│           │           │           │           │  gevent   │  Loki   │
│           │           │           │           │           │  Jaeger │
└───────────┴───────────┴───────────┴───────────┴───────────┴─────────┘
```

| 인스턴스 | 역할 | 주요 컴포넌트 |
|----------|------|--------------|
| `speedcam-app` | API 서버 + 이벤트 수신 | Django, Gunicorn, MQTT Subscriber |
| `speedcam-db` | 데이터베이스 | MySQL 8.0 (4개 DB) |
| `speedcam-mq` | 메시지 브로커 | RabbitMQ (MQTT Plugin + AMQP) |
| `speedcam-ocr` | OCR 처리 | Celery Worker (prefork pool) |
| `speedcam-alert` | 알림 처리 | Kombu Consumer + Celery Worker (gevent pool) |
| `speedcam-mon` | 모니터링 | Prometheus, Grafana, Loki, Jaeger |

### End-to-End 데이터 흐름

Rubik Pi가 GCS에 이미지를 업로드하고 MQTT로 감지 이벤트를 발행하면, Main Service가 `Detection(status=pending)` 레코드를 즉시 생성하고 OCR Task를 큐에 전달한다. OCR Worker가 번호판을 인식한 뒤 `domain_events` exchange에 `detections.completed` 이벤트를 발행하면(Choreography), Alert Service의 Kombu Consumer가 이를 수신하여 Celery gevent Worker를 통해 FCM 푸시 알림을 전송하고 알림 이력을 저장한다.

상세 시퀀스 다이어그램은 [docs/ARCHITECTURE_COMPARISON.md](docs/ARCHITECTURE_COMPARISON.md)를 참고한다.

---

## 기술 스택

| 구분 | 기술 | 버전 |
|------|------|------|
| Language | Python | 3.12 |
| Framework | Django | 5.1.7 |
| API | Django REST Framework | 3.15.2 |
| WSGI Server | Gunicorn | 23.0.0 |
| Task Queue | Celery | 5.5.2 |
| Message Broker | RabbitMQ | 3.13+ |
| RDBMS | MySQL | 8.0 |
| OCR Engine | EasyOCR | 1.7.2 |
| Image Processing | OpenCV | 4.10.0 |
| Object Storage | Google Cloud Storage | 2.18.2 |
| Push Notification | Firebase Admin SDK | 6.8.0 |
| Async Pool | gevent | 24.2.1 |
| Tracing | OpenTelemetry + Jaeger | - |
| Metrics | Prometheus + Grafana | - |
| Logging | Loki + Promtail | 3.3.2 |
| Container | Docker | 29.x |
| CI | GitHub Actions | - |

---

## 프로젝트 구조

각 서비스는 동일한 코드베이스를 공유하되, 실행 시 역할에 따라 다른 컴포넌트만 활성화한다.

```
backend/
├── .github/workflows/          # CI (lint, test, docker-build)
│   ├── lint.yml
│   ├── test.yml
│   └── docker-build.yml
│
├── apps/                       # Django Apps (서비스별 독립 DB)
│   ├── vehicles/               # → vehicles_db
│   ├── detections/             # → detections_db
│   └── notifications/          # → notifications_db
│
├── config/                     # Django / Celery 설정
│   ├── settings/               # base.py, dev.py, prod.py
│   ├── celery.py               # Exchange / Queue / Routing 정의
│   ├── db_router.py            # MSA Database Router
│   ├── urls.py
│   └── wsgi.py
│
├── core/                       # 공통 모듈
│   ├── mqtt/                   # MQTT Subscriber / Publisher
│   │   ├── subscriber.py       # detections/new 수신 → Detection 생성 → OCR 발행
│   │   └── publisher.py        # 도메인 이벤트 발행 (detections/completed)
│   ├── events/                 # AMQP 도메인 이벤트
│   │   └── consumer.py         # Kombu Consumer (Alert Service용)
│   ├── gcs/                    # Google Cloud Storage 클라이언트
│   └── firebase/               # FCM 클라이언트
│
├── tasks/                      # Celery Tasks
│   ├── ocr_tasks.py            # process_ocr (OCR Service)
│   ├── notification_tasks.py   # send_notification (Alert Service)
│   └── dlq_tasks.py            # DLQ 메시지 처리
│
├── scripts/                    # 서비스 시작 스크립트
│   ├── start_main.sh           # Django + MQTT Subscriber
│   ├── start_ocr_worker.sh     # Celery prefork Worker
│   └── start_alert_worker.sh   # Kombu Consumer + Celery gevent Worker
│
├── docker/                     # Docker / 인프라 설정
│   ├── Dockerfile.main         # Main Service 이미지
│   ├── Dockerfile.ocr          # OCR Service 이미지
│   ├── Dockerfile.alert        # Alert Service 이미지
│   ├── docker-compose.yml      # 로컬 개발 환경
│   ├── mysql/
│   │   └── init.sql            # Multi-DB 초기화
│   ├── rabbitmq/
│   │   └── enabled_plugins     # MQTT Plugin 활성화
│   └── k6/                     # 부하 테스트 스크립트
│       └── mqtt-load-test.py
│
├── tests/                      # 테스트
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── docs/                       # 설계 문서
├── credentials/                # 인증 정보 (Git 제외)
├── requirements/               # 서비스별 의존성
│   ├── base.txt                # 공통
│   ├── main.txt                # Main Service
│   ├── ocr.txt                 # OCR Service
│   └── alert.txt               # Alert Service
│
├── manage.py
├── pytest.ini
└── backend.env.example         # 환경변수 템플릿
```

---

## 로컬 개발 환경

### Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd backend

# 2. 환경변수 설정
cp backend.env.example backend.env
# backend.env를 에디터에서 편집

# 3. Docker Compose 실행
cd docker
docker-compose up -d --build

# 4. 접속 확인
# API Server:       http://localhost:8000
# Swagger UI:       http://localhost:8000/swagger/
# RabbitMQ Mgmt:    http://localhost:15672  (sa / 1234)
# Flower:           http://localhost:5555
```

### 주요 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | Django 설정 모듈 |
| `GUNICORN_WORKERS` | 4 | Gunicorn 워커 수 |
| `GUNICORN_THREADS` | 2 | 워커당 스레드 수 |
| `OCR_CONCURRENCY` | 2 | OCR Worker 프로세스 수 |
| `ALERT_CONCURRENCY` | 50 | Alert Worker greenlet 수 |
| `OCR_MOCK` | true | OCR Mock 모드 (로컬 개발용) |
| `FCM_MOCK` | true | FCM Mock 모드 (로컬 개발용) |
| `LOG_LEVEL` | info | 로깅 레벨 |

전체 환경변수 목록은 [`backend.env.example`](backend.env.example)을 참고한다.

---

## CI

GitHub Actions를 통해 `develop` 브랜치에 대한 `push` 및 `pull_request` 시 자동으로 실행된다.

| Workflow | 내용 |
|----------|------|
| `lint.yml` | flake8, black, isort 코드 품질 검사 |
| `test.yml` | pytest (main, ocr, alert 3개 워크플로우) |
| `docker-build.yml` | 3개 Docker 이미지 빌드 검증 |

CD는 별도 deploy 저장소에서 관리된다.

---

## 관련 문서

### 이 저장소 (docs/)

| 문서 | 내용 |
|------|------|
| [docs/ARCHITECTURE_COMPARISON.md](docs/ARCHITECTURE_COMPARISON.md) | Before → After 아키텍처 상세 비교 및 E2E 시퀀스 다이어그램 |
| [docs/GEVENT_DB_THREAD_SAFETY.md](docs/GEVENT_DB_THREAD_SAFETY.md) | OTel + gevent 조합의 DB thread-safety 이슈 분석 및 해결 |
| [docs/load-test-plan.md](docs/load-test-plan.md) | 시나리오별 부하 테스트 설계 및 환경 |
| [docs/performance-analysis.md](docs/performance-analysis.md) | 병목 분석 및 최적화 방향 |
| [docs/PRD.md](docs/PRD.md) | 시스템 전체 요구사항 정의서 |

### 조직 수준 문서 (.github 저장소)

아키텍처 진화 배경, 알림 설계, 부하 테스트 실측 결과 및 모니터링 스크린샷은 조직 프로필 저장소(`.github`)의 `docs/` 디렉토리에서 관리된다.
