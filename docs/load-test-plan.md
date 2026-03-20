# SpeedCam 부하 테스트 계획서

## 0. v1 vs v2 비교 테스트 전략

### 비교 목적

v1(모놀리식 동기 OCR) → v2(Event Driven Architecture) 아키텍처 전환의 성능 개선 효과를 **정량적으로 입증**하기 위해, 동일한 시나리오 구조로 양측을 테스트합니다.

### 비교 가능한 시나리오 매핑

| 비교 항목 | v1 시나리오 | v2 시나리오 | 비교 가능 | 비고 |
|----------|-----------|-----------|----------|------|
| 순수 읽기 (대시보드) | A: dashboard_polling (3 VUs) | A: dashboard_polling (3 VUs) | Yes | 동일 구조 |
| 혼합 워크로드 | C: mixed_workload (0→9 VUs) | C: mixed_workload (0→9 VUs) | Yes | 읽기/쓰기 비율 유사 |
| 스파이크 내성 | D: spike (0→15 VUs) | D: spike_resilience (0→15 VUs) | Yes | 동일 VU 프로파일 |
| 스트레스 읽기 | E: stress_ramp (0→50 VUs) | E: stress_ramp (0→50 VUs) | Yes | 동일 VU 프로파일 |
| 스트레스 혼합 | F: stress_mixed (0→50 VUs) | F: stress_mixed (0→50 VUs) | Yes | **쓰기 내용 상이*** |
| 동기 OCR 부하 | B: sync_ocr_stress (2 VUs) | N/A | No | v2는 MQTT 파이프라인으로 분리 |
| MQTT 파이프라인 | N/A | MQTT 3 시나리오 | No | v1에는 MQTT 없음 |

> *v1 stress_mixed 20% 쓰기 = **동기 OCR POST** (3~10초/건, HTTP 스레드 점유)
> v2 stress_mixed 20% 쓰기 = **차량 등록 POST** (<300ms, OCR과 무관)
> → **이 차이 자체가 핵심 비교 포인트: OCR 분리 효과**

### 비교 불가능한 영역

- **v1 sync_ocr_stress** vs **v2 admin_ops**: v1은 OCR이 HTTP 동기 처리, v2는 OCR이 별도 Worker에서 비동기 처리. 구조적으로 다른 테스트.
- **v2 MQTT 파이프라인**: v1에는 MQTT가 없으므로 직접 비교 불가. v2 전용 성능 지표.

### 핵심 비교 메트릭 매핑

| v1 메트릭 | v2 메트릭 | 의미 | 비고 |
|----------|----------|------|------|
| dashboard_req_duration | dashboard_req_duration | 대시보드 응답시간 | 공통 |
| cars_list_duration | detections_list_duration | 목록 조회 | 엔드포인트명 상이 |
| unchecked_req_duration | pending_read_duration | 미처리 목록 | 엔드포인트명 상이 |
| ocr_req_duration | N/A | 동기 OCR | v2는 MQTT 파이프라인 |
| N/A | statistics_req_duration | 통계 조회 | v2 전용 |
| stress_read_duration | stress_read_duration | 스트레스 읽기 | 공통 |
| stress_write_duration | stress_write_duration | 스트레스 쓰기 | **v1=OCR, v2=차량등록** |
| errors | errors | 에러율 | 공통 |
| total_requests | total_requests | 요청 수 | 공통 |

### 테스트 실행 순서

1. **v1 baseline 확보**: `depoly-v1/k6/load-test-v1.js` 실행 (speedcam-v1-app, 10.178.0.8)
2. **v2 HTTP 테스트**: `backend/docker/k6/load-test.js` 실행 (speedcam-app, 10.178.0.4)
3. **v2 MQTT 테스트**: `backend/docker/k6/mqtt-load-test.py` 실행
4. **결과 비교**: `performance-analysis.md` Section 5의 비교 표에 수치 기입

---

본 문서는 SpeedCam 프로젝트의 가설 기반 부하 테스트 계획을 제공합니다.

---

## 1. 시스템 아키텍처 및 용량 분석

### 인프라 구성
- 6개 GCP e2-small 인스턴스 (2 vCPU, 2 GB RAM 각각):
  - speedcam-app: Django + Gunicorn + MQTT Subscriber
  - speedcam-db: MySQL 8.0
  - speedcam-mq: RabbitMQ (MQTT plugin + AMQP)
  - speedcam-ocr: Celery OCR Worker
  - speedcam-alert: Celery Alert Worker
  - speedcam-mon: Prometheus + Grafana + Loki + Jaeger

### v1 인프라 구성 (비교 기준)

> v1과 v2는 완전히 별도 인스턴스에서 운영됩니다.

- 1개 GCP e2-standard-2 인스턴스 (2 vCPU, 4 GB RAM):
  - speedcam-v1-app (10.178.0.8 / 34.64.68.137): Django + Gunicorn (동기 OCR) + MySQL + RabbitMQ (모놀리식)
  - 별도 모니터링: Prometheus at 10.178.0.9 (v2 speedcam-mon 10.178.0.5와 다름)
- Gunicorn: 2 workers x 2 threads = 4 핸들러
- OCR: 동기 처리 (HTTP 스레드 내에서 EasyOCR 실행, 3~10초/건)
- 테스트 스크립트: `depoly-v1/k6/load-test-v1.js`

### env.example vs 배포 환경 차이

| 변수 | env.example 기본값 | 실제 배포값 | 영향 |
|------|-------------------|------------|------|
| `GUNICORN_WORKERS` | 4 | **2** | HTTP 처리 용량 절반 (8 → 4 핸들러) |
| `OCR_CONCURRENCY` | **2** | **4** | OCR 동시 처리 2배 |
| `ALERT_CONCURRENCY` | **50** | **100** | Alert gevent pool 2배 |

> **주의: 본 문서의 모든 용량 계산은 실제 배포 환경 값 기준입니다.**

### 용량 계산표 (배포 환경 기준)

| 컴포넌트 | 용량 | 산출 근거 |
|---------|------|----------|
| HTTP 동시 처리 | **4 핸들러** | 2 workers × 2 threads (GUNICORN_WORKERS=2) |
| 이론상 최대 HTTP RPS | **~40-80** | 4 핸들러 × (10-20 req/s, 응답 50-100ms 기준) |
| MQTT Subscriber 처리량 | ~50-100 msg/s | 단일 스레드: JSON 파싱 + DB 쓰기 + AMQP 발행 (~10-20ms/건) |
| OCR 파이프라인 (mock) | ~8-40 tasks/s | 4 workers × (2-10 tasks/s, mock sleep 0.1-0.5s) |
| OCR 파이프라인 (실제) | ~0.4-2 tasks/s | 4 workers × (0.1-0.5 tasks/s, EasyOCR ~2-10s) |
| Alert 파이프라인 | ~500-2000 tasks/s | Kombu Consumer (단일 스레드) → Celery gevent pool (concurrency=100) × (5-20 tasks/s, FCM mock 기준) |
| Kombu Consumer | 단일 스레드 | 이벤트 디스패치 전용 (도메인 이벤트 수신 → send_notification.delay()) |
| MySQL max_connections | 151 | MySQL 8.0 기본값 |
| 예상 DB 연결 수 (부하 시) | ~12-20 | Gunicorn(4) + OCR(4) + Alert(100, pooled) + MQTT(1) |

### 데이터 흐름

```
RaspPi MQTT publish (QoS 1)
  → RabbitMQ MQTT plugin → Django MQTT Subscriber (단일 스레드, loop_forever)
  → Detection.create(status=pending) [detections_db]
  → process_ocr.apply_async(queue=ocr_queue, priority=5)
  → OCR Worker: GCS 다운로드 → EasyOCR → 차량 매칭 [vehicles_db]
  → Detection.update(status=completed) [detections_db]
  → 도메인 이벤트 발행: detections.completed (domain_events exchange, topic)
  → Alert Worker Kombu Consumer: 이벤트 수신
  → send_notification.delay() → Celery gevent pool (fcm_queue)
  → FCM topic 브로드캐스트 + 개별 푸시
  → Notification.create() [notifications_db]
```

### 병목 예측 순위
1. **MQTT Subscriber** - 단일 스레드, 동기 DB 쓰기 (커넥션 풀링 없음)
2. **OCR Worker** - CPU 바운드, 4개 동시 처리 한정
3. **Gunicorn** - 4 핸들러, DB 연결 오버헤드
4. **MySQL** - 커넥션 풀링 없음, 부하 시 연결 폭주
5. **Alert Worker Kombu Consumer** - 단일 스레드 이벤트 디스패치, 고속 이벤트 유입 시 잠재 병목

### 사용 API 엔드포인트

| 엔드포인트 | 설명 | 비고 |
|-----------|------|------|
| `GET /api/v1/detections/` | 감지 목록 (페이지네이션, PAGE_SIZE=20) | 대시보드 폴링 |
| `GET /api/v1/detections/pending/` | 대기/처리 중 감지 목록 (페이지네이션 없음) | 파이프라인 상태 확인 |
| `GET /api/v1/detections/statistics/` | 집계 통계 (total, completed, failed, pending, avg_speed, max_speed) | 파이프라인 완료 검증 |
| `GET /api/v1/notifications/` | 알림 목록 (페이지네이션) | 대시보드 폴링 |
| `POST /api/v1/vehicles/` | 차량 등록 | 관리자 작업 |
| `PATCH /api/v1/vehicles/{id}/fcm-token/` | FCM 토큰 업데이트 | 관리자 작업 |

---

## 2. HTTP 테스트 시나리오 (k6)

### v1 HTTP 테스트 시나리오 (비교용)

> 상세 구현은 `depoly-v1/k6/load-test-v1.js` 참조

| 시나리오 | v1 설명 | VUs | v2 대응 | 비교 가능 |
|---------|--------|-----|---------|----------|
| A: 대시보드 폴링 | 3 VUs, 2분 | 3 | dashboard_polling | Yes |
| B: 동기 OCR 스트레스 | 2 VUs, 2분 | 2 | N/A (MQTT 파이프라인) | No (구조적 차이) |
| C: 혼합 워크로드 | 0→9 VUs, 2분30초 | 0→9 | mixed_workload | Yes |
| D: 스파이크 내성 | 0→15 VUs, 1분10초 | 0→15 | spike_resilience | Yes |
| E: 스트레스 읽기 | 0→50 VUs, 3분30초 | 0→50 | stress_ramp | Yes |
| F: 스트레스 혼합 | 0→50 VUs, 3분 | 0→50 | stress_mixed | Yes (쓰기 내용 상이*) |

> *v1 stress_mixed 쓰기 = 동기 OCR POST (3~10초), v2 stress_mixed 쓰기 = 차량 등록 POST (<300ms)
> → 이 차이가 핵심 비교 포인트: OCR 분리 효과

### 시나리오 A: 대시보드 폴링 (주요 읽기 부하)

**설명:** 사용자가 대시보드를 열어놓고 주기적으로 데이터를 확인하는 패턴

**트래픽 패턴:**
- 3-5 VUs
- `GET /api/v1/detections/` 매 5초
- `GET /api/v1/notifications/` 매 10초
- `GET /api/v1/detections/statistics/` 매 30초

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| p95 응답 시간 | < 200ms | 단순 페이지네이션 읽기, MySQL 인덱스 스캔 |
| 에러율 | 0% | 4 핸들러 용량 내 |
| 최대 RPS | 2-3 | sleep 간격으로 실제 RPS 매우 낮음 |
| 예상 병목 | 없음 | 4 핸들러 용량 범위 내 |

---

### 시나리오 B: 관리자 작업 (저빈도 쓰기)

**설명:** 관리자가 간헐적으로 차량을 등록하고 FCM 토큰을 업데이트하는 패턴

**트래픽 패턴:**
- 1-2 VUs
- `POST /api/v1/vehicles/` 매 30초
- `PATCH /api/v1/vehicles/{id}/fcm-token/` 매 60초

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| p95 응답 시간 | < 300ms | 저빈도 쓰기, 경합 최소 |
| 에러율 | 0% | 매우 낮은 부하 |
| 최대 RPS | < 0.1 | 30-60초 간격 |
| 예상 병목 | 없음 | - |

---

### 시나리오 C: 혼합 워크로드 (대시보드 + 파이프라인 읽기)

**설명:** 대시보드 폴링 + 관리자 작업 + 파이프라인 상태 확인이 동시에 발생하는 패턴

**트래픽 패턴:**
- 5 VUs 대시보드 폴링 + 1 VU 관리자 + 3 VU `/api/v1/detections/pending/` 조회
- 총 9 VUs

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| p95 응답 시간 | < 500ms | 9 VUs, sleep 간격으로 분산되나 피크 시 큐잉 발생 |
| 에러율 | < 1% | `/pending/`는 비페이지네이션, 응답 크기 증가 가능 |
| 최대 RPS | ~6-10 | sleep 간격으로 분산 |
| 예상 병목 | Gunicorn 핸들러 포화 (피크 시) | 9 VUs × 4 DBs = 최대 36 DB 연결 |

---

### 시나리오 D: 스파이크 내성 (급격한 트래픽 증가)

**설명:** 갑자기 사용자가 몰리는 상황 시뮬레이션

**트래픽 패턴:**
- Ramp: 0→3 (10s), 3→15 (10s), 15→15 (30s), 15→3 (10s), 3→0 (10s)
- 최대 15 VUs (4 핸들러 대비 ~3.75배 초과 구독)

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| p95 응답 시간 | < 1500ms | 15 VUs >> 4 핸들러 → 심각한 요청 큐잉 |
| 에러율 | < 10% | 핸들러 포화 + MySQL 연결 생성 오버헤드 |
| 최대 RPS | ~10-15 | 큐잉 발생하지만 처리는 지속 |
| 예상 병목 | Gunicorn worker 포화 + MySQL 연결 폭주 | - |

---

## 3. MQTT 테스트 시나리오

### 시나리오 A: 정상 운영 (20대 카메라, 1건/분)

**설명:** 평상시 트래픽. 20대 카메라가 분당 1건씩 감지

**트래픽 패턴:**
- 20 workers (카메라 1대 = 1 worker)
- 1 msg/min/worker = 총 0.33 msg/s
- 지속 시간: 120초
- 예상 총 메시지: 40건

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| 발행 성공률 | 100% | 구독자 처리량 대비 극히 낮은 부하 |
| 파이프라인 완료 시간 | 60초 이내 (전체) | OCR worker 대부분 유휴 |
| DLQ 메시지 | 0 | 안정적 처리 예상 |
| 예상 병목 | 없음 | - |

---

### 시나리오 B: 러시아워 (20대 카메라, 5건/분)

**설명:** 교통 혼잡 시간. 20대 카메라가 분당 5건씩 감지

**트래픽 패턴:**
- 20 workers, 5 msg/min/worker = 총 1.67 msg/s
- 지속 시간: 120초
- 예상 총 메시지: 200건

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| 발행 성공률 | 100% | 구독자 처리 범위 내 |
| 파이프라인 완료율 | 95% (120초 이내) | OCR 큐 약간 축적 (1.67 in vs 8-40 out) |
| DLQ 메시지 | 0 | - |
| 예상 병목 | OCR worker (mock 느린 경우) | - |

---

### 시나리오 C: 버스트 스톰 (20대 카메라, 1건/초)

**설명:** 스트레스 테스트. 모든 카메라가 초당 1건씩 동시 감지

**트래픽 패턴:**
- 20 workers, 1 msg/sec/worker = 총 20 msg/s
- 지속 시간: 60초
- 예상 총 메시지: 1200건

**가설:**
| 지표 | 예측값 | 근거 |
|------|--------|------|
| 발행 성공률 | 100% | RabbitMQ는 20 msg/s 충분히 처리 |
| OCR 큐 피크 깊이 | 200-500 | 20 msg/s 유입 vs OCR 4 concurrency (8-40/s) |
| 전체 드레인 시간 | 300초 이내 | 큐 축적 후 순차 처리 |
| 예상 병목 | MQTT Subscriber (단일 스레드 DB 쓰기) → OCR 큐 깊이 | - |

---

## 4. 가설 종합표

| 시나리오 | 유형 | 예측 최대 처리량 | 예측 p95 지연 | 예측 에러율 | 예측 병목 |
|---------|------|----------------|-------------|-----------|----------|
| A: 대시보드 폴링 | HTTP | 2-3 RPS | < 200ms | 0% | 없음 |
| B: 관리자 작업 | HTTP | < 0.1 RPS | < 300ms | 0% | 없음 |
| C: 혼합 워크로드 | HTTP | 6-10 RPS | < 500ms | < 1% | Gunicorn 핸들러 |
| D: 스파이크 내성 | HTTP | 10-15 RPS | < 1500ms | < 10% | Gunicorn + MySQL |
| A: 정상 운영 | MQTT | 0.33 msg/s | - | 0% | 없음 |
| B: 러시아워 | MQTT | 1.67 msg/s | - | 0% | OCR (경우에 따라) |
| C: 버스트 스톰 | MQTT | 20 msg/s | - | 0% | MQTT Subscriber → OCR |

---

## 5. 실행 방법

### 사전 요구사항
- k6 설치 (HTTP 테스트용)
- Python 3 + paho-mqtt 패키지 (MQTT 테스트용)
- SpeedCam 서비스 전체 가동 중
- Grafana 대시보드 접속 가능 (모니터링용)

### HTTP 부하테스트 (k6)

```bash
# 전체 시나리오 실행 (Prometheus Remote Write 포함)
# 주의: k6 v1.5.0에서 --out 플래그로 URL 전달 불가 → 환경변수 사용 필수
K6_PROMETHEUS_RW_SERVER_URL=http://10.178.0.5:9090/api/v1/write \
  k6 run --out experimental-prometheus-rw \
  --env MAIN_SERVICE_URL=http://localhost \
  backend/docker/k6/load-test.js

# Prometheus Remote Write 없이 실행 (결과는 콘솔 출력만)
k6 run --env MAIN_SERVICE_URL=http://localhost \
  backend/docker/k6/load-test.js
```

> **참고: 실행 위치별 호스트 설정**
>
> | 실행 위치 | `MAIN_SERVICE_URL` | Prometheus RW URL |
> |----------|-------------------|-------------------|
> | speedcam-app (권장) | `http://localhost` | `http://10.178.0.5:9090/api/v1/write` |
> | 외부 | `http://34.64.41.106` | `http://34.47.70.132:9090/api/v1/write` |
>
> k6를 speedcam-app에서 실행하면 네트워크 지연 없이 측정 가능하나,
> k6 자체가 CPU/메모리를 소비하므로 결과에 영향을 줄 수 있습니다 (e2-small 공유).

### MQTT 파이프라인 테스트

> **speedcam-app 인스턴스에서 실행 시** 내부 IP 사용:
> `speedcam-mq` → `10.178.0.7`, `speedcam-app` → `localhost`

```bash
# 정상 운영 시나리오 (speedcam-app에서 실행)
python3 mqtt-load-test.py \
  --scenario normal \
  --mqtt-host 10.178.0.7 \
  --mqtt-user sa --mqtt-pass $RABBITMQ_PASS \
  --api-url http://localhost \
  --rabbitmq-api http://10.178.0.7:15672 \
  --rabbitmq-user sa --rabbitmq-pass $RABBITMQ_PASS

# 러시아워 시나리오
python3 mqtt-load-test.py \
  --scenario rush_hour \
  --mqtt-host 10.178.0.7 \
  --mqtt-user sa --mqtt-pass $RABBITMQ_PASS \
  --api-url http://localhost \
  --rabbitmq-api http://10.178.0.7:15672 \
  --rabbitmq-user sa --rabbitmq-pass $RABBITMQ_PASS

# 버스트 스톰 시나리오
python3 mqtt-load-test.py \
  --scenario burst \
  --mqtt-host 10.178.0.7 \
  --mqtt-user sa --mqtt-pass $RABBITMQ_PASS \
  --api-url http://localhost \
  --rabbitmq-api http://10.178.0.7:15672 \
  --rabbitmq-user sa --rabbitmq-pass $RABBITMQ_PASS

# 커스텀 설정 (하위 호환)
python3 mqtt-load-test.py \
  --workers 10 --rate 5 --duration 30 \
  --mqtt-host 10.178.0.7 --mqtt-user sa --mqtt-pass $RABBITMQ_PASS
```

### 동시 실행 (HTTP + MQTT)
```bash
# 터미널 1: HTTP 부하 (speedcam-app에서 실행)
K6_PROMETHEUS_RW_SERVER_URL=http://10.178.0.5:9090/api/v1/write \
  k6 run --out experimental-prometheus-rw \
  --env MAIN_SERVICE_URL=http://localhost \
  load-test.js

# 터미널 2: MQTT 부하 (동시 실행)
python3 mqtt-load-test.py --scenario rush_hour \
  --mqtt-host 10.178.0.7 --mqtt-user sa --mqtt-pass $RABBITMQ_PASS \
  --api-url http://localhost \
  --rabbitmq-api http://10.178.0.7:15672 \
  --rabbitmq-user sa --rabbitmq-pass $RABBITMQ_PASS
```

### 테스트 중 모니터링

| 도구 | 내부 IP (GCE 내) | 외부 IP (브라우저) | 용도 |
|------|-----------------|------------------|------|
| **Grafana** | `10.178.0.5:3000` | `34.47.70.132:3000` | 대시보드 (cAdvisor, k6, Django) |
| **Prometheus** | `10.178.0.5:9090` | `34.47.70.132:9090` | 메트릭 직접 쿼리 |
| **RabbitMQ** | `10.178.0.7:15672` | `34.64.183.199:15672` | 큐 깊이, 메시지 속도 |
| **Flower** | `10.178.0.4:5555` | `34.64.41.106:5555` | Celery 태스크 현황 |

---

## 6. 테스트 후 분석 템플릿

### 가설 vs 실제 비교표

각 시나리오 실행 후 아래 표를 복사하여 채워 넣으세요.

```
시나리오: [시나리오 이름]
실행 일시: [YYYY-MM-DD HH:MM]
실행 환경: [인스턴스 사양, 특이사항]

| 지표 | 가설 | 실제 | 차이 | 분석 |
|------|------|------|------|------|
| 최대 처리량 (RPS/msg/s) | | | | |
| p95 응답 시간 | | | | |
| 에러율 | | | | |
| 예상 병목 | | | | |
| OCR 큐 피크 깊이 | | | | |
| FCM 큐 피크 깊이 | | | | |
| DLQ 메시지 수 | | | | |
| E2E 완료 시간 | | | | |
```

### 병목 식별 체크리스트

- [ ] Gunicorn worker 포화 여부 → Grafana: container CPU/memory for speedcam-app
- [ ] MySQL 연결 수 확인 → `SHOW PROCESSLIST` 또는 mysqld-exporter 메트릭
- [ ] RabbitMQ 큐 깊이 → Management UI: ocr_queue, fcm_queue, dlq_queue
- [ ] MQTT Subscriber 처리 지연 → APP 컨테이너 로그에서 on_message 처리 시간
- [ ] OCR Worker 처리 속도 → Celery exporter: task latency, queue length
- [ ] Alert Worker 처리 속도 → Celery exporter: fcm_queue task latency
- [ ] 디스크 I/O → cAdvisor: disk read/write bytes
- [ ] 메모리 부족 → cAdvisor: container memory usage vs limit

### 다음 단계 의사결정 트리

```
가설과 실제가 일치하는가?
├─ YES → 용량 한계를 정확히 파악함. 필요시 스케일링 계획 수립.
└─ NO → 왜 다른가?
    ├─ 실제가 가설보다 좋음 → 용량 계산이 보수적. 가설 수정 후 재테스트.
    ├─ 실제가 가설보다 나쁨
    │   ├─ 에러율 높음 → 병목 체크리스트로 원인 파악
    │   │   ├─ Gunicorn 포화 → GUNICORN_WORKERS 증가 또는 인스턴스 업그레이드
    │   │   ├─ MySQL 연결 폭주 → CONN_MAX_AGE 설정 또는 커넥션 풀링 도입
    │   │   ├─ OCR 큐 축적 → OCR_CONCURRENCY 증가 또는 인스턴스 분리
    │   │   └─ MQTT Subscriber 병목 → 멀티스레드 처리 또는 비동기 DB 쓰기
    │   └─ 지연시간 높음 → 동일 병목 체크리스트 적용
    └─ 패턴이 예상과 다름 → 데이터 흐름 재분석, 로그 확인
```

---

## 7. 테스트 환경 참고사항

- `OCR_MOCK=true`, `FCM_MOCK=true` 환경에서 테스트 가정 (기본)
- 실제 EasyOCR/FCM 사용 시 처리량이 크게 달라짐 (OCR: ~10-50배 느림)
- 모든 인스턴스 e2-small (2 vCPU, 2 GB RAM) — 프로덕션 환경에서는 스케일업 필요
- MySQL 커넥션 풀링 미설정 (`CONN_MAX_AGE=0`) — 고부하 시 연결 오버헤드 발생
- MQTT Subscriber 단일 스레드 — 메시지 처리 직렬화됨
- **Alert Worker 구성: Kombu Consumer (단일 스레드, 도메인 이벤트 수신) + Celery gevent pool (concurrency=100, FCM 발송)**
  - Kombu Consumer는 `detections.completed` 이벤트를 수신하여 `send_notification.delay()` 호출
  - gevent pool은 FCM 발송 I/O 바운드 작업을 비동기 처리
  - `OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH=patch_all` 설정 필요 (gevent DB 스레드 안전성 — `docs/GEVENT_DB_THREAD_SAFETY.md` 참조)
- k6를 대상 서버와 동일 인스턴스에서 실행하면 CPU/메모리 경합 발생 (별도 인스턴스 권장)
