# 성능 테스트 가이드

SpeedCam IoT 백엔드의 성능, 안정성, 파이프라인 처리 능력을 검증하기 위한 종합 가이드입니다. HTTP API 부하 테스트(k6)와 IoT 파이프라인 부하 테스트(MQTT)를 다룹니다.

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [모니터링 대시보드](#2-모니터링-대시보드)
3. [HTTP API 부하 테스트 (k6)](#3-http-api-부하-테스트-k6)
4. [IoT 파이프라인 부하 테스트 (MQTT)](#4-iot-파이프라인-부하-테스트-mqtt)
5. [End-to-End 검증 체크리스트](#5-end-to-end-검증-체크리스트)
6. [트러블슈팅](#6-트러블슈팅)
7. [정리 및 종료](#7-정리-및-종료)

---

## 1. 사전 준비

### 1.1 필요 도구

| 도구 | 용도 | 설치 방법 |
|------|------|----------|
| Docker | 컨테이너 실행 | https://docs.docker.com/get-docker/ |
| Docker Compose | 다중 컨테이너 관리 | Docker Desktop 포함 |
| Python 3.x | MQTT 파이프라인 테스트 | 기본 설치됨 |
| paho-mqtt | MQTT 클라이언트 | `pip install paho-mqtt` |
| curl | API 요청 테스트 | 기본 설치됨 |

### 1.2 환경 시작

**중요**: `docker-compose.yml`이 `speedcam-network`를 생성하고, `docker-compose.monitoring.yml`은 이를 `external: true`로 참조합니다. 반드시 순서대로 또는 `-f` 플래그로 함께 시작하세요.

```bash
# 방법 1: 앱 + 모니터링 함께 시작 (권장)
cd docker
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

```bash
# 방법 2: 순차 시작
cd docker
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.monitoring.yml up -d
```

### 1.3 macOS 참고사항

- **cAdvisor는 Linux 전용**: `docker-compose.monitoring.yml`에 `profiles: [linux]`가 설정되어 있으므로 macOS에서는 자동 제외됩니다
- **Linux에서 cAdvisor 포함**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --profile linux up -d
  ```
- **권장 Docker Desktop 메모리**: 8GB 이상

### 1.4 서비스 상태 확인

```bash
# 전체 컨테이너 상태 확인
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml ps
```

**예상 상태**: 모든 컨테이너가 `Up` 상태

```bash
# Prometheus 타겟 상태 확인
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Prometheus Scrape Targets:')
for t in data['data']['activeTargets']:
    status = '✓ UP' if t['health'] == 'up' else '✗ DOWN'
    print(f\"  {t['labels']['job']:20s} {t['health']:5s} {t['labels']['instance']}\")
"
```

**예상 출력**:
```
Prometheus Scrape Targets:
  django               up     main:8000
  otel-collector       up     otel-collector:8889
  rabbitmq             up     rabbitmq:15692
  mysql                up     mysqld-exporter:9104
  celery               up     celery-exporter:9808
  cadvisor             up     cadvisor:8080          (Linux only)
```

---

## 2. 모니터링 대시보드

### 2.1 접속 정보

| 서비스 | URL | 인증 | 용도 |
|--------|-----|------|------|
| **Grafana** | http://localhost:3000 | admin / admin | 통합 대시보드 (메트릭, 로그, 트레이스) |
| **Prometheus** | http://localhost:9090 | 없음 | 메트릭 저장소 및 PromQL 쿼리 |
| **Jaeger** | http://localhost:16686 | 없음 | 분산 트레이싱 UI |
| **RabbitMQ** | http://localhost:15672 | sa / 1234 | 큐 모니터링 |
| **Flower** | http://localhost:5555 | 없음 | Celery 태스크 모니터링 |

### 2.2 Grafana 대시보드 Import

시작 시 자동으로 대시보드가 프로비저닝되지만, 추가 대시보드는 수동 import:

1. Grafana 접속: http://localhost:3000
2. Dashboards → New → Import
3. Dashboard ID 입력:

| 대시보드 | ID | 데이터소스 | 용도 |
|---------|-----|-----------|------|
| Django Prometheus | 17658 | Prometheus | HTTP 요청, 응답시간, 에러율 |
| Celery Monitoring | 17509 | Prometheus | 태스크 성공/실패, 큐 깊이 |
| RabbitMQ Overview | 10991 | Prometheus | 메시지 rate, 큐 깊이 |
| MySQL Overview | 14057 | Prometheus | 쿼리 수, 커넥션, 슬로우 쿼리 |
| K6 Load Testing | 19665 | Prometheus | k6 부하 테스트 결과 (실시간) |

### 2.3 주요 메트릭 보기

**Django HTTP 메트릭** (자동 수집):
```
http://localhost:3000/d/<dashboard-id>
```

**Jaeger 트레이스** (요청 플로우 추적):
```
http://localhost:16686 → Services → speedcam-api → 최근 트레이스 보기
```

**Loki 로그** (구조화된 로그):
```
Grafana → Explore → Data source: Loki
쿼리: {service="main"}
```

---

## 3. HTTP API 부하 테스트 (k6)

### 3.1 테스트 대상

REST API 엔드포인트 검증 (IoT 파이프라인 제외):

| 엔드포인트 | 메서드 | 용도 |
|-----------|--------|------|
| `/health/` | GET | 헬스 체크 |
| `/api/v1/vehicles/` | GET, POST, PUT, DELETE | 차량 CRUD |
| `/api/v1/detections/` | GET | 검출 목록 조회 |
| `/api/v1/notifications/` | GET | 알림 목록 조회 |

### 3.2 설치

paho-mqtt는 MQTT 테스트에만 필요합니다. k6 테스트는 Docker 컨테이너에서 실행되므로 호스트 설치 불필요합니다.

### 3.3 실행 방법

```bash
cd docker

# 기본 실행: Prometheus에 결과 기록
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/load-test.js
```

**선택 사항**: 환경 변수 오버라이드

```bash
# 커스텀 대상 서버 지정
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run -e MAIN_SERVICE_URL=http://localhost:8000 k6 \
  run --out experimental-prometheus-rw /scripts/load-test.js
```

### 3.4 시나리오별 테스트

`load-test.js`에 3가지 시나리오가 정의되어 있습니다. 각 시나리오는 startTime이 다르므로 한 번의 실행으로 모두 테스트됩니다.

| 시나리오 | VU 범위 | 시간 | 시작 시간 | 용도 | 기대 결과 |
|----------|---------|------|----------|------|----------|
| **smoke** | 1 | 10초 | 0s | 기본 동작 확인 | 에러 0%, 응답 <100ms |
| **average_load** | 0→10→0 | ~100초 | 15s | 평균 부하 검증 | p95 <500ms, 에러 <1% |
| **spike** | 0→30→0 | ~25초 | 120s | 스파이크 처리 능력 | p99 <1000ms, 에러 <5% |

**총 실행 시간**: ~2분 30초

### 3.5 실행 중 모니터링

실시간으로 다른 터미널에서 메트릭 확인:

```bash
# Prometheus UI에서 확인
open http://localhost:9090/graph
# 쿼리: rate(k6_http_reqs_total[1m])
```

```bash
# Grafana K6 대시보드 (ID: 19665) 보기
open http://localhost:3000/d/K6-dashboard
```

### 3.6 결과 해석

k6 실행 완료 후 stdout에 요약이 표시됩니다:

```
     checks.........................: 100.00% ✓ 5000  ✗ 0
     data_received..................: 1.2 MB  ✓
     data_sent.......................: 850 kB  ✓
     http_req_blocked...............: avg=1.2ms   min=100µs   max=50ms   p(90)=2.1ms   p(95)=3.5ms
     http_req_connecting............: avg=0.8ms   min=0µs     max=40ms   p(90)=1.5ms   p(95)=2.2ms
     http_req_duration..............: avg=125ms   min=50ms    max=2s     p(90)=350ms   p(95)=450ms
     http_req_failed................: 0.00% ✓ 0    ✗ 5000
     http_req_receiving.............: avg=2.5ms   min=0.5ms   max=20ms   p(90)=4ms     p(95)=5ms
     http_req_sending...............: avg=0.5ms   min=0.1ms   max=5ms    p(90)=1ms     p(95)=1ms
     http_req_tls_handshaking.......: avg=0ms     min=0µs     max=0s     p(90)=0s      p(95)=0s
     http_req_waiting...............: avg=122ms   min=48ms    max=1.9s   p(90)=348ms   p(95)=448ms
     http_reqs.......................: 5000    199.31/s
     iteration_duration.............: avg=2.5s    min=2s      max=30s    p(90)=2.8s    p(95)=3.1s
     iterations......................: 5000    199.31/s
```

**주요 메트릭**:
- `checks`: 테스트 검증 통과율 (100%이어야 함)
- `http_req_duration` (p95): 95% 요청의 응답시간 (목표 <500ms)
- `http_req_failed`: 실패율 (0%이어야 함)
- `http_reqs`: 초당 처리한 요청 수 (RPS)

### 3.7 맞춤형 시나리오 작성

`load-test.js`를 수정하여 커스텀 시나리오를 추가할 수 있습니다. 자세한 내용은 [k6 공식 문서](https://k6.io/docs/get-started/running-k6/)를 참고하세요.

---

## 4. IoT 파이프라인 부하 테스트 (MQTT)

### 4.1 테스트 대상

실제 IoT 카메라 동작을 시뮬레이션하여 전체 파이프라인을 검증합니다:

```
MQTT 메시지 발행 (Raspberry Pi 시뮬)
    ↓
RabbitMQ 큐에 저장
    ↓
Detection 생성 (pending)
    ↓
OCR Worker (이미지 처리)
    ↓
Alert Worker (FCM 알림)
    ↓
완료 (completed)
```

### 4.2 사전 준비

**호스트에서 실행하는 경우**:
```bash
pip install paho-mqtt
```

### 4.3 실행 방법

**기본 실행** (호스트):
```bash
python docker/k6/mqtt-load-test.py \
  --workers 5 \
  --rate 2 \
  --duration 60
```

**환경 변수 오버라이드**:
```bash
MQTT_HOST=localhost MQTT_PORT=1883 python docker/k6/mqtt-load-test.py \
  --workers 5 --rate 2 --duration 60
```

### 4.4 테스트 단계별 파라미터

| 단계 | Workers | Rate(/s) | Duration | 총 메시지 | 용도 | 예상 처리 시간 |
|------|---------|----------|----------|-----------|------|----------------|
| **Smoke** | 1 | 1 | 10s | ~10 | 기본 동작 확인 | ~30초 |
| **Load** | 5 | 2 | 60s | ~600 | 일반 부하 검증 | ~5분 |
| **Stress** | 20 | 5 | 120s | ~12,000 | 시스템 한계 확인 | ~30분 |
| **Soak** | 5 | 2 | 3600s | ~36,000 | 장시간 안정성 | ~2시간 |

**추천 시작 순서**:
1. Smoke 테스트로 연결성 확인
2. Load 테스트로 정상 동작 확인
3. Stress 테스트로 한계 확인

### 4.5 메시지 형식

MQTT 메시지는 다음 JSON 형식으로 발행됩니다:

```json
{
  "camera_id": "CAM-001",
  "location": "서울시 강남구 테헤란로",
  "detected_speed": 95.3,
  "speed_limit": 60.0,
  "detected_at": "2024-01-01T12:00:00+09:00",
  "image_gcs_uri": "gs://speedcam-bucket/detections/1704067200000-1234.jpg"
}
```

**필드 설명**:
- `camera_id`: 카메라 ID (CAM-001 ~ CAM-020)
- `location`: 카메라 위치 (실제 한국 도로명)
- `detected_speed`: 감지된 속도 (제한속도 + 5~50km/h 초과)
- `speed_limit`: 해당 구간 제한속도 (60, 80, 100, 110 중 선택)
- `detected_at`: ISO 8601 형식의 감지 시간 (한국 표준시)
- `image_gcs_uri`: GCS에 저장된 이미지 경로 (시뮬레이션용 경로)

### 4.6 실행 중 모니터링

테스트 실행 중 다른 터미널에서 진행 상황을 모니터링합니다:

**RabbitMQ 큐 상태**:
```bash
curl -s -u sa:1234 http://localhost:15672/api/queues/%2F | python3 -c "
import json, sys
queues = json.load(sys.stdin)
print('RabbitMQ Queue Status:')
for q in queues:
    if q['name'] in ('detections_queue', 'ocr_queue', 'fcm_queue'):
        print(f\"  {q['name']:20s} messages={q.get('messages', 0):6d} consumers={q.get('consumers', 0)}\")
"
```

**Celery 태스크 상태**:
```bash
curl -s http://localhost:5555/api/workers | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Celery Workers:')
for worker, info in data.items():
    print(f\"  {worker:30s} {info.get('status', 'unknown')}\")
"
```

**Jaeger 트레이스 (선택)**:
```bash
open http://localhost:16686
# Services → speedcam-api → Detection 또는 OCR 작업 선택
```

### 4.7 결과 확인

MQTT 테스트 완료 후 stdout에 통계가 표시됩니다:

```
=== MQTT Load Test Complete ===
Total Published: 600
Failed: 0
Success Rate: 100.00%
Avg Latency: 245ms
Min Latency: 50ms
Max Latency: 1200ms
Total Duration: 65 seconds
Messages/sec: 9.23
```

**해석**:
- **Success Rate**: 100%이어야 함 (메시지 발행 성공)
- **Avg Latency**: MQTT 발행 시간 (네트워크 지연)
- **Total Duration**: 부하 테스트 총 소요 시간

---

## 5. End-to-End 검증 체크리스트

MQTT 부하 테스트 실행 후 다음 항목들을 확인하여 파이프라인이 정상 동작하는지 검증합니다.

### 5.1 Detection 처리 상태

```bash
# 전체 Detection 조회
curl -s http://localhost:8000/api/v1/detections/ | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Total Detections: {data['count']}\")
print()

# 상태별 카운트 추출
results = data['results']
status_counts = {}
for r in results:
    status = r.get('ocr_status', 'unknown')
    status_counts[status] = status_counts.get(status, 0) + 1

print('Status Distribution:')
for status, count in sorted(status_counts.items()):
    print(f\"  {status:15s}: {count:4d}\")
"
```

**정상 상태**:
- 대부분이 `completed` 상태
- 일부 `processing` 또는 `pending` (최근 생성된 건)
- `failed` 건이 있으면 OCR Worker 로그 확인: `docker logs speedcam-ocr`

```bash
# 최근 생성된 Detection 확인
curl -s "http://localhost:8000/api/v1/detections/?ordering=-detected_at&limit=5" | \
  python3 -m json.tool | head -50
```

### 5.2 Jaeger 분산 트레이스 확인

트레이스를 통해 요청이 전체 시스템을 거치는 과정을 추적합니다.

```bash
# 사용 가능한 서비스 확인
curl -s http://localhost:16686/api/services | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Jaeger Services:')
for service in data['data']:
    print(f\"  - {service}\")
"
```

**예상 서비스**:
- `speedcam-api`: Django 메인 애플리케이션
- `speedcam-ocr`: OCR Worker (Celery)
- `speedcam-alert`: Alert Worker (Celery)

```bash
# 최근 트레이스 조회 (speedcam-api)
curl -s "http://localhost:16686/api/traces?service=speedcam-api&limit=3" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Recent Traces (speedcam-api):')
for trace in data['data'][:3]:
    trace_id = trace['traceID'][:16]
    num_spans = len(trace['spans'])
    operation = trace['spans'][0]['operationName']
    duration_ms = (trace['spans'][0]['endTime'] - trace['spans'][0]['startTime']) / 1000
    print(f\"  {trace_id}... | Spans: {num_spans:2d} | {operation:30s} | {duration_ms:6.1f}ms\")
"
```

**정상 구성**:
- Health Check: 1-2 spans (빠름)
- Vehicle Create: 3-5 spans (DB 쿼리 포함)
- Detection Create: 5-10 spans (MQTT, RabbitMQ, DB)
- OCR Task: 7-15 spans (GCS, API, DB)

### 5.3 Loki 로그 확인

구조화된 로그를 통해 각 컴포넌트의 동작을 확인합니다.

```bash
# Loki에서 수집된 로그 스트림 확인
curl -sG http://localhost:3100/loki/api/v1/labels | python3 -c "
import json, sys
data = json.load(sys.stdin)
print('Loki Labels:')
print(f\"  Available labels: {', '.join(data['data'][:5])}...\")
"
```

```bash
# speedcam 컨테이너의 최근 로그 (Loki)
curl -sG "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={container=~"speedcam.*"}' \
  --data-urlencode 'limit=10' | python3 -c "
import json, sys
data = json.load(sys.stdin)
streams = data['data']['result']
print(f'Log Streams Found: {len(streams)}')
for stream in streams[:3]:
    container = stream['stream'].get('container', 'unknown')
    num_entries = len(stream['values'])
    print(f\"  {container:30s}: {num_entries} log entries\")
"
```

**Grafana UI에서 로그 보기**:
1. Grafana → Explore → Loki
2. 쿼리: `{container=~"speedcam.*"}`
3. 각 로그 라인의 `trace_id=` 클릭 → Jaeger 트레이스 자동 이동

### 5.4 RabbitMQ 큐 상태

MQTT 메시지 처리 파이프라인의 큐 상태를 확인합니다.

```bash
# 큐별 메시지 수 확인
curl -s -u sa:1234 http://localhost:15672/api/queues/%2F | python3 -c "
import json, sys
queues = json.load(sys.stdin)
print('RabbitMQ Queue Status:')
print(f\"{'Queue Name':<20} {'Messages':>10} {'Consumers':>10} {'Ready':>10} {'Unacked':>10}\")
print('-' * 60)
for q in queues:
    if q['name'] in ('detections_queue', 'ocr_queue', 'fcm_queue', 'dlq_queue'):
        name = q['name']
        msgs = q.get('messages', 0)
        consumers = q.get('consumers', 0)
        ready = q.get('messages_ready', 0)
        unacked = q.get('messages_unacknowledged', 0)
        print(f'{name:<20} {msgs:>10} {consumers:>10} {ready:>10} {unacked:>10}')
"
```

**정상 상태**:
- **detections_queue**: 0 (Detection 생성 후 즉시 처리)
- **ocr_queue**: 0-10 (처리 중)
- **fcm_queue**: 0-5 (처리 중)
- **dlq_queue**: 0 (에러 없음)
- **consumers**: 각 큐당 1 이상 (worker가 리스닝 중)

### 5.5 Prometheus 메트릭 확인

시스템 성능 메트릭을 Prometheus PromQL로 확인합니다.

```bash
# Django HTTP 요청 메트릭
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=rate(django_http_requests_total[5m])' | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data['data']['result']
if result:
    print(f'Django HTTP Request Rate: {len(result)} series found')
    print(f'  Current RPS: {float(result[0][\"value\"][1]):.1f}')
else:
    print('No Django metrics found')
"
```

```bash
# Celery 태스크 메트릭
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=rate(celery_tasks_total[5m])' | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data['data']['result']
if result:
    print(f'Celery Task Rate: {len(result)} series found')
    for r in result[:3]:
        state = r['metric'].get('state', 'unknown')
        rate = float(r['value'][1])
        print(f\"  {state:10s}: {rate:.1f} tasks/sec\")
else:
    print('No Celery metrics found')
"
```

### 5.6 DB 성능 메트릭

```bash
# MySQL 활성 커넥션 수
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=mysql_global_status_threads_connected' | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data['data']['result']
if result:
    value = float(result[0]['value'][1])
    print(f'Active MySQL Connections: {int(value)}')
else:
    print('No MySQL metrics found')
"
```

### 5.7 컨테이너 리소스 사용률

```bash
# 각 컨테이너 CPU 사용률 (%) - cAdvisor 필요
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=rate(container_cpu_usage_seconds_total{name=~"speedcam-.*"}[5m])*100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data['data']['result']
if result:
    print('Container CPU Usage (%):')
    for r in result[:5]:
        name = r['metric'].get('name', 'unknown')
        cpu_usage = float(r['value'][1])
        print(f\"  {name:30s}: {cpu_usage:6.2f}%\")
else:
    print('No cAdvisor metrics found (Linux only)')
"
```

```bash
# 각 컨테이너 메모리 사용량 (MB) - cAdvisor 필요
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=container_memory_usage_bytes{name=~"speedcam-.*"}/1024/1024' | python3 -c "
import json, sys
data = json.load(sys.stdin)
result = data['data']['result']
if result:
    print('Container Memory Usage (MB):')
    for r in result[:5]:
        name = r['metric'].get('name', 'unknown')
        memory_mb = float(r['value'][1])
        print(f\"  {name:30s}: {memory_mb:7.1f} MB\")
else:
    print('No cAdvisor metrics found (Linux only)')
"
```

---

## 6. 트러블슈팅

### 6.1 docker-compose 실행 오류

**오류**: `network speedcam-network not found`

**원인**: 모니터링 스택만 단독으로 시작함

**해결**:
```bash
# 앱 스택을 먼저 시작
docker compose -f docker-compose.yml up -d

# 그 다음 모니터링 추가
docker compose -f docker-compose.monitoring.yml up -d

# 또는 함께 시작
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

### 6.2 Prometheus 타겟이 DOWN

**오류**: Prometheus 대시보드에서 일부 타겟이 DOWN 상태

**celery-exporter가 재시작되는 경우**:
- **원인**: RabbitMQ보다 먼저 시작되어 broker 연결 실패
- **해결**: 자동 복구됨 (`restart: unless-stopped`). 30초 기다린 후 확인

**mysqld-exporter가 DOWN**:
- **원인**: MySQL보다 먼저 시작됨
- **해결**: 자동 복구됨. 30초 기다린 후 확인

**django가 DOWN**:
- **원인**: 앱 시작 실패
- **해결**:
  ```bash
  docker logs speedcam-main
  ```

### 6.3 cAdvisor 시작 실패 (macOS)

**오류**: `cadvisor: error setting oom score: open /proc/.../oom_score_adj: no such file or directory`

**원인**: cAdvisor는 Linux 전용이며 /proc 파일시스템 필요

**해결**: 예상 동작. macOS에서는 자동으로 제외됨 (`profiles: [linux]`). Linux에서만 실행하세요.

### 6.4 Jaeger에 트레이스가 없음

**오류**: Jaeger UI에서 데이터가 보이지 않음

**원인**: OTEL_EXPORTER_OTLP_ENDPOINT 미설정

**해결**:
```bash
# backend.env 확인
cat docker/backend.env | grep OTEL_EXPORTER_OTLP_ENDPOINT

# 없으면 추가
echo 'OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317' >> docker/backend.env

# 앱 재시작
docker compose -f docker-compose.yml up -d --force-recreate speedcam-main
```

### 6.5 Loki 429 Too Many Requests

**오류**: Loki 쿼리 실패 with 429 status

**원인**: 로그 스트림이 너무 많음 (한계 초과)

**해결**:
```bash
# loki-config.yml에서 한계 증가
# docker/monitoring/loki/loki-config.yml 수정
# limits_config:
#   max_global_streams_per_user: 20000  # 기본값 10000에서 증가
```

### 6.6 환경 변수 변경 후 반영 안됨

**오류**: backend.env 변경 후 앱에 반영 안됨

**원인**: Docker restart는 env_file을 다시 읽지 않음

**해결**:
```bash
# --force-recreate 사용
docker compose -f docker-compose.yml up -d --force-recreate speedcam-main
```

### 6.7 MQTT 연결 실패

**오류**: `python mqtt-load-test.py` 실행 시 연결 실패

**원인**: RabbitMQ MQTT 플러그인 미활성화

**확인**:
```bash
docker logs speedcam-rabbitmq | grep -i mqtt
# "MQTT plugin loaded" 메시지가 있어야 함
```

**해결** (이미 자동 활성화됨):
docker-compose.yml의 rabbitmq command에 `rabbitmq_mqtt` 플러그인이 포함되어 있는지 확인

### 6.8 k6 테스트 타임아웃

**오류**: k6 테스트 중 `dial tcp: lookup main: no such host`

**원인**: k6 컨테이너가 speedcam-network에 연결되지 않음

**해결**: docker-compose.monitoring.yml에서 k6 서비스가 올바른 네트워크 설정이 있는지 확인

```yaml
networks:
  - speedcam-network  # speedcam-network 참조
```

---

## 7. 정리 및 종료

### 7.1 전체 종료 및 데이터 제거

```bash
cd docker

# 컨테이너 + 볼륨 완전 제거
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down -v
```

### 7.2 모니터링 데이터만 삭제

런타임 데이터(Prometheus, Grafana, Loki)를 초기화합니다:

```bash
rm -rf docker/monitoring/prometheus/data \
       docker/monitoring/loki/data \
       docker/monitoring/grafana/data
```

다시 시작하면 초기 상태로 복구됩니다.

### 7.3 모니터링 스택만 종료 (앱 유지)

앱은 계속 실행하고 모니터링만 종료:

```bash
cd docker

docker compose -f docker-compose.monitoring.yml down
```

나중에 모니터링을 다시 시작:

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

### 7.4 특정 컨테이너만 종료

```bash
# 개별 서비스 종료
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  stop speedcam-main speedcam-ocr

# 개별 서비스 재시작
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  restart speedcam-main
```

---

## 8. 추가 자료

### 8.1 관련 문서

- [모니터링 스택 가이드](./MONITORING.md): 아키텍처, 설정, 메트릭 상세 설명
- [배포 가이드](./DEPLOYMENT.md): GCP 멀티 인스턴스 배포 방법
- [아키텍처 비교](./ARCHITECTURE_COMPARISON.md): 시스템 설계 이유

### 8.2 외부 자료

- [k6 공식 문서](https://k6.io/docs/)
- [Prometheus PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana 대시보드](https://grafana.com/grafana/dashboards/)
- [Jaeger 분산 트레이싱](https://www.jaegertracing.io/docs/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)

### 8.3 자주 사용하는 명령어

```bash
# 모니터링 스택 전체 확인
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml ps

# 로그 실시간 추적
docker logs -f speedcam-main
docker logs -f speedcam-ocr
docker logs -f speedcam-alert

# 모니터링 데이터 초기화 후 재시작
rm -rf docker/monitoring/*/data
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Prometheus 메트릭 직접 조회
curl -s http://localhost:9090/api/v1/query --data-urlencode 'query=<PROMQL>'

# RabbitMQ 큐 확인
curl -s -u sa:1234 http://localhost:15672/api/queues/%2F

# Jaeger 서비스 확인
curl -s http://localhost:16686/api/services

# Docker 디스크 정리 (주의: 사용하지 않는 모든 이미지/볼륨 제거)
docker system prune -a --volumes
```

---

## 9. FAQ

**Q: k6과 MQTT 테스트 중 어느 것을 먼저 실행해야 하나요?**

A: k6을 먼저 실행하세요. k6은 REST API만 테스트하므로 (순수 읽기 작업) 데이터베이스 상태에 영향을 주지 않습니다. MQTT 테스트는 실제 Detection을 생성하므로 나중에 실행하는 것이 좋습니다.

**Q: 부하 테스트 중 시스템이 느려집니다. 어떻게 해야 하나요?**

A: 정상입니다. 먼저 메트릭을 확인하세요:
1. Prometheus에서 CPU/메모리 사용률 확인
2. RabbitMQ 큐 깊이 확인 (메시지 밀림)
3. MySQL 커넥션 풀 상태 확인
4. 필요하면 docker-compose.yml의 리소스 제한(`resources`) 조정

**Q: 테스트 결과를 저장하고 싶습니다.**

A: k6은 자동으로 Prometheus에 메트릭을 기록합니다. Prometheus → Export로 데이터를 JSON/CSV로 내보낼 수 있습니다. MQTT 테스트의 경우 stdout을 파일로 리다이렉트합니다:
```bash
python docker/k6/mqtt-load-test.py ... > test_results.txt
```

**Q: 모니터링 없이 성능 테스트를 실행할 수 있나요?**

A: 가능합니다. k6 또는 MQTT 테스트 스크립트는 독립적으로 실행할 수 있습니다. 하지만 모니터링 없으면 결과를 측정하고 분석하기 어렵습니다.

**Q: 프로덕션 환경에서 어떻게 테스트하나요?**

A: 이 가이드는 로컬/개발 환경 기준입니다. 프로덕션 배포는 [GCP 멀티 인스턴스 배포 가이드](./DEPLOYMENT.md)를 참고하세요. 프로덕션에서는:
1. 전용 모니터링 인스턴스 사용
2. Prometheus 보안 설정 (인증, TLS)
3. 백그라운드에서 정기적인 스모크 테스트 실행
4. 알림 규칙(Alert) 설정

---

마지막 업데이트: 2024년 1월
