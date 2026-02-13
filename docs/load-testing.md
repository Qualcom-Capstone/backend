# SpeedCam 부하 테스트 전략

## 개요

SpeedCam은 IoT 카메라에서 MQTT를 통해 이미지를 수신하고, Django 애플리케이션이 AMQP/Celery를 통해 OCR 작업을 처리한 후, 감지된 결과를 Alert Service로 전달하는 완전한 파이프라인 아키텍처입니다. 이 문서는 이 복잡한 시스템의 성능을 검증하고 병목 지점을 식별하기 위한 부하 테스트 전략을 설명합니다.

## 시스템 아키텍처

### 처리 파이프라인

```
IoT Camera (MQTT)
    ↓
Main Service (Django + Gunicorn + MQTT Subscriber)
    ↓
AMQP/Celery Queue
    ↓
OCR Worker (EasyOCR on CPU)
    ↓
AMQP Domain Event (detections.completed)
    ↓
Alert Service (kombu consumer → FCM)
```

### 배포 인프라 (GCE asia-northeast3-a)

| 인스턴스 | 역할 | 핵심 설정 |
|---------|------|---------|
| **speedcam-app** | Django + Gunicorn + MQTT Subscriber | GUNICORN_WORKERS=2 |
| **speedcam-db** | MySQL 8.0 데이터베이스 | - |
| **speedcam-mq** | RabbitMQ (MQTT plugin + AMQP) | - |
| **speedcam-ocr** | Celery OCR Worker (EasyOCR) | OCR_CONCURRENCY=1 |
| **speedcam-alert** | Domain Event Consumer → FCM | FCM_MOCK=true |
| **speedcam-mon** | 모니터링 스택 | Prometheus, Grafana, Loki, Jaeger |

## 측정된 성능 기준치 (Baselines)

현재 환경에서 측정된 주요 성능 메트릭:

| 메트릭 | 값 | 설명 |
|-------|-----|------|
| **MQTT 발행 지연** | ~0.3ms | 카메라에서 브로커까지의 지연 시간 |
| **OCR 처리 시간** | 4-5s | 캐시된 EasyOCR Reader로 단일 이미지 처리 |
| **OCR 모델 초기 로딩** | ~30s | EasyOCR 모델 처음 로드 시간 |
| **OCR 최대 처리량** | ~0.2 msg/s | CONCURRENCY=1 설정에서의 이론적 한계 |
| **Alert 이벤트 처리** | <1s | detections.completed 이벤트에서 FCM 전송까지 |
| **엔드-투-엔드 지연** | ~5-6s | MQTT 발행에서 Alert 완료까지 전체 파이프라인 |

## 테스트 시나리오

부하 테스트는 다양한 부하 프로파일 하에서 시스템의 동작을 검증하기 위해 5개의 시나리오로 구성됩니다.

### 시나리오 정의표

| 시나리오 | 워커 수 | 전송률 | 지속시간 | 총 메시지 수 | 목표 및 검증 사항 |
|---------|--------|-------|---------|------------|-----------------|
| **smoke** | 1 | 1 msg (수동) | - | 1 | 파이프라인 기본 동작 검증 |
| **baseline** | 1 | 0.2/s | 60s | ~12 | OCR 최대 처리량 수준에서 안정성 검증 |
| **saturation** | 3 | 1/s | 60s | ~180 | OCR 워커 포화 상태 시뮬레이션 |
| **spike** | 5 | 2/s | 10s | ~100 | 갑작스러운 트래픽 증가 대응 능력 검증 |
| **sustained** | 2 | 0.5/s | 300s | ~300 | 장시간 안정적 운영 능력 검증 |

### 각 시나리오의 상세 설명

#### 1. Smoke Test (스모크 테스트)
- **목적**: 파이프라인이 정상 작동하는지 기본 검증
- **가설**: 단일 메시지는 지연 없이 전체 파이프라인을 통과
- **수행 방법**: 수동으로 하나의 MQTT 메시지 발행
- **검증 항목**:
  - 메시지가 speedcam-app에서 수신됨
  - Celery 작업이 생성됨
  - OCR 처리 완료
  - Alert 이벤트가 발행됨
  - 종단간 지연이 ~5-6초 범위

#### 2. Baseline Test (기준선 테스트)
- **목적**: OCR 워커의 이론적 최대 처리량에서 안정성 검증
- **가설**: OCR_CONCURRENCY=1 설정에서 0.2 msg/s 지속 가능
- **초기화**: speedcam-ocr 워커 재시작하여 모델 미리 로드
- **수행 방법**: 1개 워커가 12개 메시지를 60초에 걸쳐 0.2/s 속도로 발행
- **검증 항목**:
  - 모든 메시지가 처리됨 (100% 완료율)
  - 큐 깊이가 안정적으로 유지됨
  - 데이터베이스 연결이 누적되지 않음
  - 종단간 지연이 안정적 (5-6초 범위)

#### 3. Saturation Test (포화 테스트)
- **목적**: OCR 워커 포화 상태에서 시스템의 대응 능력 검증
- **가설**: 1/s 속도로 메시지가 쌓이면 큐 깊이 증가하며, 메시지 손실 없이 처리됨
- **수행 방법**: 3개 워커가 180개 메시지를 60초에 걸쳐 1/s 속도로 발행
- **검증 항목**:
  - 큐 최대 깊이 관찰 (이론값: ~12)
  - 메시지 손실 0건
  - 종단간 지연 증가 추이 (선형 증가 예상)
  - Celery 작업 타임아웃 발생 여부
  - 데이터베이스 연결 고갈 여부

#### 4. Spike Test (스파이크 테스트)
- **목적**: 갑작스러운 트래픽 급증에 대한 시스템 회복 능력 검증
- **가설**: 짧은 기간의 고속 전송 후 시스템이 정상으로 복구
- **수행 방법**: 5개 워커가 100개 메시지를 10초에 걸쳐 2/s 속도로 발행
- **검증 항목**:
  - 스파이크 중 큐 최대 깊이
  - 메시지 손실 여부
  - 완료 후 큐 정상화 시간
  - 메모리 누수 증상 (메모리 사용량 회귀)

#### 5. Sustained Test (지속성 테스트)
- **목적**: 장시간 안정적 운영 능력 검증 및 메모리 누수 감지
- **가설**: 0.5/s 지속 속도로 300초 동안 모든 메시지 처리, 메모리 누수 없음
- **수행 방법**: 2개 워커가 300개 메시지를 300초에 걸쳐 0.5/s 속도로 발행
- **검증 항목**:
  - 메시지 처리율 일정 유지 (100%)
  - 메모리 사용량 추이 (증가 아닌 안정)
  - CPU 사용률 안정성
  - 완료된 메시지 수 = 300건

## 가설-실행-비교 프레임워크

부하 테스트는 다음의 명확한 프레임워크를 따릅니다:

### 1. 사전 가설 수립 (Pre-Test Hypothesis)

각 시나리오 시작 전에 예상 결과를 명확히 정의합니다:

```
테스트 시작 전:
├─ 예상 완료 메시지 수
├─ 예상 최대 큐 깊이
├─ 예상 종단간 지연 범위
├─ 예상 리소스 사용률 범위
└─ 예상 오류율 (0% 또는 허용 범위)
```

테스트 스크립트는 다음과 같이 가설을 출력합니다:

```python
# 예시
print(f"""
=== Baseline Test Hypothesis ===
Expected Message Completion: 12 (100%)
Expected Queue Depth: <1 (stable)
Expected E2E Latency: 5-6 seconds
Expected Error Rate: 0%
Expected OCR Processing Time: ~4-5s per image
Resource Baseline: Monitor CPU and Memory
""")
```

### 2. 테스트 실행 (Test Execution)

실시간으로 시스템 상태를 모니터링하면서 테스트를 실행합니다:

```
테스트 진행 중:
├─ 메시지 발행률 확인
├─ 실시간 큐 깊이 모니터링
├─ Celery 작업 상태 추적
├─ 에러 로그 감시
└─ 리소스 사용률 관찰
```

테스트 스크립트는 진행 상황을 실시간으로 출력합니다:

```
[T+5s] Published: 1/12 | Queue Depth: 0 | OCR Processing: 1 | Completed: 0
[T+10s] Published: 2/12 | Queue Depth: 0 | OCR Processing: 1 | Completed: 1
[T+15s] Published: 3/12 | Queue Depth: 1 | OCR Processing: 1 | Completed: 1
...
```

### 3. 결과 비교 및 분석 (Comparison & Analysis)

테스트 완료 후, 실제 결과를 사전 가설과 비교합니다:

#### 파이프라인 검증 쿼리

테스트 완료 후 데이터베이스를 직접 쿼리하여 메시지 처리 상황을 확인합니다:

```sql
-- Detection 테이블 확인 (OCR 처리된 메시지)
SELECT
    COUNT(*) as total_detections,
    COUNT(CASE WHEN status='completed' THEN 1 END) as completed,
    COUNT(CASE WHEN status='failed' THEN 1 END) as failed,
    COUNT(CASE WHEN status='processing' THEN 1 END) as still_processing
FROM detections
WHERE created_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE);

-- 시간별 처리 완료 현황
SELECT
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:00') as minute,
    COUNT(*) as completed_count
FROM detections
WHERE status='completed' AND created_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE)
GROUP BY DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:00')
ORDER BY minute;

-- 처리 시간 분석
SELECT
    MIN(DATE_FORMAT(TIMEDIFF(updated_at, created_at), '%H:%i:%s')) as min_duration,
    MAX(DATE_FORMAT(TIMEDIFF(updated_at, created_at), '%H:%i:%s')) as max_duration,
    AVG(TIME_TO_SEC(TIMEDIFF(updated_at, created_at))) as avg_seconds
FROM detections
WHERE status='completed' AND created_at > DATE_SUB(NOW(), INTERVAL 10 MINUTE);
```

#### 결과 비교표

테스트 결과를 가설과 비교하는 형식:

```
=== Baseline Test Results ===
Metric                  | Hypothesis    | Actual        | Status  | Analysis
Total Messages          | 12 (100%)     | 12 (100%)     | PASS    | All messages processed
Queue Depth Peak        | <1            | 0             | PASS    | No queuing observed
E2E Latency Range       | 5-6s          | 5.2-5.8s      | PASS    | Within expected range
Error Rate              | 0%            | 0%            | PASS    | No processing errors
OCR Processing Time     | 4-5s avg      | 4.6s avg      | PASS    | Consistent with baseline
Memory Leak             | None          | Stable        | PASS    | No memory increase
DB Connections          | <5            | 2-3           | PASS    | No connection pooling issues
```

### 4. 의사결정 기준

결과 비교 후 다음 단계를 결정합니다:

| 결과 | 의사결정 |
|-----|--------|
| **모두 PASS** | 다음 시나리오 진행 |
| **부분 FAIL (메시지 처리 완료)** | 병목 분석 후 진행 (성능 개선 필요) |
| **메시지 손실** | 중단 및 구성 검토 필요 |
| **시스템 크래시** | 중단 및 디버깅 필요 |

## 테스트 실행 방법

### 사전 요구사항

```bash
# GCE 인스턴스에 SSH 접속
gcloud compute ssh speedcam-app --zone=asia-northeast3-a

# Docker 컨테이너 내부 접속
sudo docker exec -it speedcam-main bash

# 환경 변수 설정
export MQTT_PASS=<MQTT 브로커 비밀번호>
export MQTT_HOST=speedcam-mq
export MQTT_PORT=1883
```

### 테스트 스크립트 위치

```
/app/docker/k6/mqtt-load-test.py     # 주요 테스트 스크립트
/app/docker/k6/load-test.js          # k6 HTTP API 테스트 (보조)
```

### 시나리오별 실행 명령

#### 1. Smoke Test (스모크 테스트)

```bash
# 모든 서비스 준비 상태 확인
python /app/docker/k6/mqtt-load-test.py smoke

# 예상 출력:
# === Smoke Test Starting ===
# Publishing 1 test message...
# [T+0.5s] Message published
# [T+5s] Detection created in database
# [T+5.5s] Alert event published
# === Smoke Test PASSED ===
```

#### 2. Baseline Test (기준선 테스트)

```bash
# OCR 워커가 모델을 미리 로드하도록 대기 (약 30초)
# 모니터링 터미널에서 Grafana 대시보드 준비

python /app/docker/k6/mqtt-load-test.py baseline

# 예상 소요 시간: 약 70초 (60초 + 처리 완료 대기)
# 예상 완료 메시지: 12건
```

#### 3. Saturation Test (포화 테스트)

```bash
# 주의: 이 테스트는 큐 깊이를 증가시킵니다
# 모니터링 대시보드 확인 준비

python /app/docker/k6/mqtt-load-test.py saturation

# 예상 소요 시간: 약 150초 (60초 + 큐 처리 완료 대기)
# 예상 완료 메시지: 180건
```

#### 4. Spike Test (스파이크 테스트)

```bash
# 단기간 높은 처리율 테스트

python /app/docker/k6/mqtt-load-test.py spike

# 예상 소요 시간: 약 90초 (10초 + 큐 처리 완료 대기)
# 예상 완료 메시지: 100건
```

#### 5. Sustained Test (지속성 테스트)

```bash
# 장시간 안정성 테스트 - 커피를 준비하세요
# 이 테스트는 약 8-10분 소요됩니다

python /app/docker/k6/mqtt-load-test.py sustained

# 예상 소요 시간: 약 600초 (300초 + 큐 처리 완료 대기)
# 예상 완료 메시지: 300건
```

### 테스트 중단 및 정리

```bash
# 테스트를 강제 중단해야 하는 경우 (Ctrl+C)
# Celery 큐에 남아있는 작업을 확인
python -c "from celery_app import app; print(app.control.inspect().active())"

# 필요시 큐 초기화 (주의: 처리 중인 작업도 제거됨)
python -c "from celery_app import app; app.control.purge()"

# 데이터베이스 테스트 데이터 정리
python manage.py shell
>>> from detections.models import Detection
>>> Detection.objects.filter(created_at__gt=timezone.now()-timedelta(hours=1)).delete()
```

## 결과 해석 및 성능 분석

### 메트릭 정의

#### 완료 메시지 (Completed Messages)
- 정의: MQTT 발행에서 FCM Alert까지 전체 파이프라인 완료
- PASS 기준: 예상 메시지 수의 100%
- FAIL 기준: 1건 이상의 메시지 손실

#### 큐 깊이 (Queue Depth)
- 정의: RabbitMQ AMQP 큐에 대기 중인 Celery 작업 수
- 모니터링: `rabbitmqctl list_queues` 또는 Grafana
- 분석:
  - Baseline에서 큐 깊이 > 2: OCR 처리 능력 부족
  - Saturation에서 큐 깊이 선형 증가: 예상된 동작
  - Sustained 후 큐 깊이 0으로 복귀: 정상 종료

#### 종단간 지연 (End-to-End Latency)
- 정의: MQTT 발행부터 Alert 완료까지의 경과 시간
- 측정: Database detection.created_at → alert_events.published_at
- 분석:
  - Baseline: 5-6초 (안정적)
  - Saturation: 5초 + (큐_깊이 × 4초) (선형 증가)
  - Spike 후 정상화: 초기 지연 증가 → 정상 복귀

#### 오류율 (Error Rate)
- 정의: 처리 실패한 메시지 비율
- PASS 기준: 0%
- 감지 방법:
  - Celery 작업 failed 상태
  - Loki 로그의 ERROR, EXCEPTION 레벨
  - Database detection.status='failed'

### 결과별 해석 가이드

#### Baseline Test 결과 해석

**완전 통과 (All PASS)**
```
완료: 12/12 (100%)
큐 최대: 0
E2E 지연: 5.2-5.8s 평균 5.5s
오류율: 0%

→ 해석: 시스템이 설계된 대로 동작. OCR 최대 처리량을 안전하게 유지.
→ 다음: Saturation 테스트 진행.
```

**부분 실패 (Partial FAIL) - 메시지 손실 없음**
```
완료: 12/12 (100%)
큐 최대: 1-2
E2E 지연: 5.5-7.2s 평균 6.2s
오류율: 0%

→ 해석: 메시지는 모두 처리되지만 약간의 지연 발생.
→ 원인 분석:
   - 데이터베이스 연결 대기
   - GC pause 영향
   - MQTT 브로커 내부 처리 지연
→ 다음: Grafana에서 상세 분석 (CPU, 메모리, DB 연결)
```

**실패 (FAIL) - 메시지 손실**
```
완료: 10/12 (83%)
손실: 2
큐 최대: 5+
오류율: 16.7%

→ 해석: 메시지 손실 발생 - 심각한 문제.
→ 즉시 조치:
   1. Celery 워커 로그 확인
      docker logs speedcam-ocr | tail -100
   2. Loki에서 ERROR 레벨 로그 검색
      {job="celery-worker"} | json | status="ERROR"
   3. RabbitMQ 상태 확인
      docker exec speedcam-mq rabbitmqctl status
→ 다음: 원인 제거 후 Baseline 재실행.
```

#### Saturation Test 결과 해석

**정상 포화 (Expected Behavior)**
```
완료: 180/180 (100%)
큐 최대: 8-12 (이론값: (1.0-0.2)×60 = 48s×1msg/s ≈ 10-12)
E2E 지연: 초기 5-6s → 최대 50-52s
오류율: 0%

→ 해석: OCR이 포화되었으나 메시지 손실 없음 (큐 기반 처리).
→ 시스템이 설계된 대로 부하를 흡수.
→ 다음: Spike 테스트 진행.
```

**예상과 다른 포화 (Anomaly)**
```
완료: 180/180 (100%)
큐 최대: >30 (예상 10-12)
E2E 지연: 100초 이상
오류율: 0% 하지만 일부 타임아웃

→ 해석: OCR 처리 속도가 예상보다 느림.
→ 원인 분석:
   - OCR 모델 재로드되었을 가능성 (메모리 부족)
   - CPU 과부하 또는 열 제한
   - 데이터베이스 슬로우 쿼리
→ 다음: 인프라 점검 후 baseline 재실행.
```

### 병목 지점 식별 및 개선

#### 현재 알려진 병목: OCR 처리 (Primary Bottleneck)

**증상:**
- OCR_CONCURRENCY=1로 설정되어 있음
- 이론적 최대 처리량: 0.2 msg/s (4-5초/이미지)
- 단일 CPU 코어에서 순차 처리

**개선 방안:**

```bash
# 1단계: 멀티코어 EasyOCR (실험)
# Saturation 결과를 토대로 확인
# 큐가 10개 이상 쌓이면 다음 단계 고려

# 2단계: OCR_CONCURRENCY 증가 (권장)
# speedcam-ocr 환경 변수 수정
export OCR_CONCURRENCY=2  # 이론상 0.4 msg/s 가능

# Docker 재시작
sudo docker restart speedcam-ocr

# Baseline 재테스트
python /app/docker/k6/mqtt-load-test.py baseline

# 결과: 완료 시간 50% 단축 예상 (12 × 5s / 2 = 30s)
```

**OCR_CONCURRENCY 증가 시 고려사항:**
- 메모리 사용량 증가 (각 워커당 GiB급)
- CPU 코어 수 제한 (GCE 인스턴스 코어 수 확인)
- 온도 및 열 제한 (GPU 없이 CPU만 사용)

#### 2차 병목: Gunicorn 워커 (Secondary Bottleneck)

**현재 상태:**
- GUNICORN_WORKERS=2 설정
- MQTT 수신은 별도 스레드에서 처리
- HTTP API는 Gunicorn 워커 풀 공유

**확인 방법:**
```bash
# Saturation 테스트 중 Grafana 확인
# Gunicorn worker utilization을 모니터링
# 만약 모든 워커가 항상 바쁘다면:

# 로그에서 "worker timeout" 확인
docker logs speedcam-app 2>&1 | grep -i timeout

# 필요시 GUNICORN_WORKERS 증가
export GUNICORN_WORKERS=4
```

#### 3차 병목: MySQL 데이터베이스 (Tertiary Bottleneck)

**감지:**
```sql
-- 데이터베이스 연결 확인
SHOW PROCESSLIST;

-- 슬로우 쿼리 확인
SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 10;

-- 테이블 락 확인
SHOW OPEN TABLES WHERE In_use > 0;
```

**개선:**
```bash
# 1. 인덱스 확인
# detections 테이블의 created_at, status에 인덱스 있는지 확인

# 2. 연결 풀 크기 확인
# Django DATABASES 설정의 CONN_MAX_AGE

# 3. 필요시 마스터-슬레이브 구성 검토
```

#### MQTT Subscriber 병목 가능성

**현재 아키텍처:**
- Django 애플리케이션 내부 MQTT 클라이언트 (단일 스레드)
- 블로킹 구독 모델

**부하 테스트에서 영향:**
- 메시지 발행률이 초당 1개 이상일 때 순차 처리
- 단일 스레드이므로 CPU 활용도가 낮을 수 있음

**확인:**
```bash
# 테스트 중 프로세스 상태 확인
docker top speedcam-app | head -20

# 만약 MQTT 수신 thread가 항상 busy면:
# MQTT 클라이언트 최적화 필요
```

## 모니터링 및 관찰

### Grafana 대시보드 사용

테스트 진행 중 다음 대시보드를 지속적으로 관찰합니다:

#### 1. SpeedCam 애플리케이션 대시보드

```
URL: http://speedcam-mon:3000/d/speedcam-app/speedcam-application

주요 패널:
├─ MQTT Messages Received (per second)
│  └─ 값이 설정된 발행율과 일치하는지 확인
├─ Celery Queue Depth (tasks)
│  └─ Baseline: ~0, Saturation: 8-12, Spike: 최대값 관찰
├─ OCR Processing Time (histogram)
│  └─ 평균값이 4-5초 범위인지 확인
└─ End-to-End Latency (percentiles)
   └─ P50: 5-6초, P99: 큐_깊이에 비례하여 증가
```

#### 2. RabbitMQ 모니터링 대시보드

```
URL: http://speedcam-mq:15672 (username: guest, password: guest)

관찰 항목:
├─ Queue: celery (Messages)
│  └─ Ready: 처리 대기 중인 작업
│  └─ Unacked: 처리 중인 작업
├─ Queue: detections.completed
│  └─ Alert Service가 처리하는 이벤트 흐름
└─ Consumers
   └─ OCR Worker 연결 상태 확인
```

#### 3. MySQL 성능 모니터링

```
Grafana 패널: Database Performance

확인 항목:
├─ Queries per second
├─ Average query execution time
├─ Active connections
├─ Slow queries (>1 second)
└─ Innodb buffer pool hit ratio (>99% 목표)
```

### Prometheus 메트릭 쿼리

테스트 중 다음 메트릭을 직접 쿼리하여 확인합니다:

```promql
# MQTT 수신 메시지율
rate(mqtt_messages_received_total[1m])

# Celery 큐 깊이 (현재값)
celery_queue_length{queue="celery"}

# OCR 처리 시간 (평균)
rate(ocr_processing_time_seconds_sum[5m]) /
rate(ocr_processing_time_seconds_count[5m])

# 완료된 감지 이벤트
rate(detections_completed_total[1m])

# Alert 발행 이벤트
rate(alert_events_published_total[1m])

# 데이터베이스 연결
mysql_global_status_threads_connected
```

### Loki 로그 쿼리

오류 또는 의심스러운 동작을 추적하기 위해 다음 로그 쿼리를 사용합니다:

```loki
# OCR 워커 에러
{job="celery-worker"} | json | level="ERROR"

# Celery 작업 타임아웃
{job="celery-worker"} | json | msg=~".*timeout.*"

# Django 애플리케이션 에러
{job="django-app"} | json | level="ERROR"

# MQTT 연결 문제
{job="django-app"} | json | msg=~".*mqtt.*error.*"

# 데이터베이스 연결 에러
{job="django-app"} | json | msg=~".*database.*connection.*"

# 지난 5분간의 모든 ERROR 레벨 로그 개수
count(
  {job=~"celery-worker|django-app"}
  | json
  | level="ERROR"
) by (job)
```

### Jaeger 분산 추적 (Distributed Tracing)

선택적으로 완전한 요청 흐름을 추적합니다:

```
URL: http://speedcam-mon:6831/search

추적 항목:
1. MQTT 메시지 수신 스팬
   ├─ MQTT publish (IoT Camera)
   ├─ MQTT message received (Django)
   └─ Celery task enqueue

2. OCR 처리 스팬
   ├─ Celery task start
   ├─ EasyOCR model load (초회)
   ├─ Image preprocessing
   ├─ OCR inference
   └─ Celery task complete

3. Alert 발행 스팬
   ├─ Domain event created
   ├─ kombu consumer received
   ├─ FCM API call
   └─ Alert published
```

## 문제 해결 및 FAQ

### Q: Baseline 테스트에서 메시지가 처리되지 않음

**A: 다음을 순서대로 확인하세요:**

```bash
# 1. MQTT 브로커 연결 확인
docker exec speedcam-mq mosquitto_sub -h localhost -t "#" &
# (다른 터미널에서) python /app/docker/k6/mqtt-load-test.py smoke

# 2. Celery 워커 상태 확인
docker exec speedcam-ocr celery -A ocr_tasks inspect active

# 3. Django 애플리케이션 로그 확인
docker logs speedcam-app | tail -50 | grep -i error

# 4. RabbitMQ 큐 상태
docker exec speedcam-mq rabbitmqctl list_queues
```

### Q: OCR 워커가 응답하지 않음

**A:**

```bash
# 1. EasyOCR 모델 로드 상태 확인
# 첫 테스트 실행 시 약 30초 소요 (로그에서 확인)
docker logs speedcam-ocr | grep -i "loading\|model"

# 2. 메모리 부족 여부 확인
docker stats speedcam-ocr

# 만약 메모리 사용량이 95% 이상:
# OCR_CONCURRENCY를 1로 유지하거나
# 인스턴스 메모리 증설 필요

# 3. 워커 재시작
docker restart speedcam-ocr

# 모델 다시 로드될 때까지 대기 (30초)
sleep 30
python /app/docker/k6/mqtt-load-test.py smoke
```

### Q: 테스트 중 "Task timed out" 에러 발생

**A:**

```bash
# 1. Celery 타임아웃 설정 확인
# celery_config.py의 task_soft_time_limit, task_time_limit 확인

# 2. 원인별 대응:
# - OCR 처리 시간 > 5초인 경우: 정상 (이미지 크기 또는 모델 특성)
# - OCR 처리 시간 > 30초인 경우: 모델 재로드 또는 하드웨어 문제
#   → docker restart speedcam-ocr

# 3. 타임아웃 시간 증가 (필요시)
export CELERY_TASK_TIME_LIMIT=600  # 10분
docker restart speedcam-ocr
```

### Q: 메모리 사용량이 계속 증가함

**A: 메모리 누수 가능성**

```bash
# 1. 현재 메모리 사용량 추이 확인
watch -n 1 'docker stats speedcam-app --no-stream | head -2'

# 2. Grafana에서 Memory Usage 그래프 확인
# Sustained 테스트 후 메모리가 복구되지 않으면 누수 가능

# 3. 원인 분석:
# - Database 연결 누적: Django ORM 미사용 연결
#   → Django 설정의 CONN_MAX_AGE 확인
#
# - Celery 작업 메타데이터 누적
#   → RabbitMQ 퍼지 또는 설정 검토
#
# - Python 객체 참조 순환
#   → 메모리 프로파일링 도구 (memory_profiler) 사용

# 4. 재시작
docker restart speedcam-app speedcam-ocr speedcam-alert
```

### Q: Saturation 테스트 후 큐가 비지 않음

**A:**

```bash
# 1. 남아있는 작업 확인
docker exec speedcam-mq rabbitmqctl list_queues

# 2. Celery 워커 상태 확인
docker exec speedcam-ocr celery -A ocr_tasks inspect active

# 3. 만약 워커가 멈춘 경우:
docker restart speedcam-ocr

# 4. 큐 수동 퍼지 (데이터 손실 주의)
docker exec speedcam-mq rabbitmqctl purge_queue celery

# 5. 데이터베이스 정리
docker exec speedcam-app python manage.py shell
# >>> from detections.models import Detection
# >>> Detection.objects.filter(created_at__gt=...).delete()
```

## 체크리스트

테스트를 시작하기 전에 다음을 확인하세요:

### 사전 점검

- [ ] 모든 인스턴스(speedcam-app, speedcam-db, speedcam-mq, speedcam-ocr, speedcam-alert, speedcam-mon)가 실행 중
- [ ] SSH 접속 가능 (`gcloud compute ssh speedcam-app --zone=asia-northeast3-a`)
- [ ] Docker 컨테이너 접속 가능 (`docker exec -it speedcam-main bash`)
- [ ] MQTT 환경 변수 설정 (`MQTT_PASS` 포함)
- [ ] RabbitMQ 웹 UI 접속 가능 (http://speedcam-mq:15672)
- [ ] Grafana 접속 가능 (http://speedcam-mon:3000)
- [ ] MySQL 접속 가능 (`docker exec speedcam-db mysql -u root -p`)

### 테스트별 점검

#### Smoke Test 전
- [ ] Celery 워커 상태: active/idle
- [ ] RabbitMQ 큐: celery, detections.completed 모두 empty
- [ ] 데이터베이스: 최근 detections 없음

#### Baseline Test 전
- [ ] OCR 모델 미리 로드 (약 30초 대기 후 확인)
- [ ] Grafana 대시보드 새로고침
- [ ] 모니터링 터미널 준비 (2개: 스크립트 + 로그)

#### Saturation Test 전
- [ ] Spike 테스트 완료 후 큐 비워짐 확인
- [ ] 메모리 사용량 정상 범위 확인
- [ ] Grafana 범위 설정 변경 (Y축 스케일 확인)

#### Spike Test 전
- [ ] 최근 테스트 결과 분석 완료
- [ ] 병목 지점 파악 완료

#### Sustained Test 전
- [ ] 충분한 시간 확보 (약 10분)
- [ ] 모니터링 도구 안정성 확인
- [ ] 로그 수집 설정 확인 (Loki)

### 테스트 후 정리

- [ ] 모든 완료 메시지 수 기록
- [ ] 최대 큐 깊이 기록
- [ ] 주요 오류 로그 저장
- [ ] Grafana 스크린샷 캡처
- [ ] 분석 결과 문서화
- [ ] 데이터베이스 테스트 데이터 정리 (필요시)
- [ ] 다음 테스트 시나리오 계획

## 결론 및 권장사항

### 현재 성능 프로필 요약

SpeedCam 시스템은 다음과 같은 성능 특성을 보입니다:

- **최대 안전 처리 속도**: ~0.2 msg/s (OCR 병목)
- **포화 상태 큐 깊이**: ~10-12 작업
- **종단간 지연**: 5-6초 (baseline) ~ 50초+ (saturation)
- **안정성**: 메시지 손실 0%, 메모리 누수 없음

### 향후 개선 계획

**Phase 1 (즉시 실행 가능)**
1. OCR_CONCURRENCY를 2로 증가 → 처리량 2배 증대
2. Baseline 테스트 재실행하여 안정성 재검증

**Phase 2 (중장기)**
1. 이미지 전처리 최적화 (해상도, 압축율)
2. EasyOCR 대신 더 빠른 OCR 엔진 평가 (TrOCR, PaddleOCR)
3. GPU 활용 검토 (GCE GPU 인스턴스)

**Phase 3 (장기)**
1. 마이크로서비스 아키텍처: OCR 서비스 독립 스케일링
2. 메시지 브로커 클러스터링
3. 캐싱 전략 (이미지 해시 기반 캐시 완료 결과)

## 참고 자료

- MQTT 메시지 형식: `/app/docs/mqtt-protocol.md`
- Celery 설정: `/app/celery_config.py`
- Django MQTT Subscriber: `/app/mqtt/subscriber.py`
- OCR 워커 구현: `/app/ocr/tasks.py`
- Grafana 대시보드 설정: `/app/docker/grafana/dashboards/`
- Loki 설정: `/app/docker/loki/loki-config.yaml`

---

**작성일**: 2026년 2월 13일
**최종 수정**: 2026년 2월 13일
**유지보수자**: SpeedCam 팀
