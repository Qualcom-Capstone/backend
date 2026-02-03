# 모니터링 스택 가이드

## 1. 아키텍처 개요

```
App Services (main, ocr-worker, alert-worker)
    │ OTLP gRPC (:4317)
    ▼
OTel Collector ──traces──► Jaeger (:16686) ──► Grafana (:3000)
    │                                              ▲
    └──metrics──► Prometheus (:9090) ──────────────┘
                      ▲                            │
cAdvisor ─────────────┤                    Loki (:3100) ◄── Promtail
Django /metrics ──────┤                            ▲
RabbitMQ :15692 ──────┤                     Docker logs
mysqld-exporter ──────┤
celery-exporter ──────┘

K6 (부하테스트) ──prometheus remote write──► Prometheus
```

---

## 2. 서비스 구성

### 2.1 전체 서비스 목록

| 서비스 | 이미지 | 포트 | 역할 |
|--------|--------|------|------|
| **otel-collector** | `otel/opentelemetry-collector-contrib:0.98.0` | 4317 (gRPC), 4318 (HTTP), 8889 | 트레이스/메트릭 수집 허브 |
| **jaeger** | `jaegertracing/all-in-one:1.57` | 16686 (UI), 14250 | 분산 트레이싱 저장/UI |
| **prometheus** | `prom/prometheus:v2.51.2` | 9090 | 메트릭 수집/저장/쿼리 |
| **grafana** | `grafana/grafana:10.4.2` | 3000 | 통합 대시보드 |
| **loki** | `grafana/loki:2.9.6` | 3100 | 로그 집계/저장 |
| **promtail** | `grafana/promtail:2.9.6` | - | Docker 로그 → Loki 전송 |
| **cadvisor** | `gcr.io/cadvisor/cadvisor:v0.49.1` | 8080 | 컨테이너 리소스 메트릭 |
| **mysqld-exporter** | `prom/mysqld-exporter:v0.15.1` | 9104 | MySQL 메트릭 노출 |
| **celery-exporter** | `danihodovic/celery-exporter:0.10.3` | 9808 | Celery 큐/태스크 메트릭 |
| **k6** | `grafana/k6:latest` | - | 부하 테스트 (on-demand) |

### 2.2 Prometheus Scrape Targets

| Job | Target | 수집 항목 |
|-----|--------|-----------|
| `django` | `main:8000/metrics` | HTTP 요청 수, 응답 시간, DB 쿼리 수 |
| `otel-collector` | `otel-collector:8889` | OTel에서 변환된 앱 메트릭 |
| `rabbitmq` | `rabbitmq:15692` | 큐 깊이, 메시지 rate, 커넥션, 채널 |
| `mysql` | `mysqld-exporter:9104` | 쿼리 수, 커넥션, InnoDB 버퍼, 슬로우 쿼리 |
| `celery` | `celery-exporter:9808` | 태스크 성공/실패, 실행 시간, 큐 길이 |
| `cadvisor` | `cadvisor:8080` | 컨테이너 CPU, 메모리, 네트워크 I/O |

---

## 3. 실행 방법

### 3.1 기본 서비스만 (모니터링 없이)

```bash
cd docker
docker compose up -d
```

앱은 모니터링 스택 없이도 정상 동작함. OTel Collector에 연결 실패해도 앱은 죽지 않음 (graceful fallback).

### 3.2 모니터링 포함

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

### 3.3 부하 테스트 포함 (k6)

```bash
# k6 서비스는 profiles: [loadtest] 이므로 명시적 실행 필요
cd docker
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/smoke.js
```

### 3.4 모니터링만 재시작 (앱 유지)

```bash
cd docker
docker compose -f docker-compose.monitoring.yml restart prometheus grafana
```

---

## 4. 접속 정보

| 서비스 | URL | 인증 |
|--------|-----|------|
| **Grafana** | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | 없음 |
| **Jaeger** | http://localhost:16686 | 없음 |
| **RabbitMQ Management** | http://localhost:15672 | sa / 1234 |
| **Flower** | http://localhost:5555 | 없음 |
| **cAdvisor** | http://localhost:8080 | 없음 |
| **Django /metrics** | http://localhost:8000/metrics | 없음 |

---

## 5. Prometheus 타겟 확인

### 5.1 UI에서 확인

```
http://localhost:9090/targets
```

6개 job이 모두 **UP** (초록색)이면 정상.

### 5.2 API로 확인

```bash
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json, sys
data = json.load(sys.stdin)
for t in data['data']['activeTargets']:
    print(f\"{t['labels']['job']:20s} {t['labels']['instance']:30s} {t['health']}\")
"
```

### 5.3 타겟이 DOWN일 때

| 증상 | 원인 | 해결 |
|------|------|------|
| django DOWN | main 컨테이너 미기동 또는 django-prometheus 미설치 | `docker logs speedcam-main` 확인 |
| rabbitmq DOWN | rabbitmq_prometheus 플러그인 미활성화 | docker-compose.yml의 command에 `rabbitmq_prometheus` 포함 확인 |
| mysql DOWN | mysqld-exporter 인증 실패 | `.my.cnf` 파일의 user/password 확인 |
| celery DOWN | celery-exporter가 broker 연결 실패 | RabbitMQ 기동 여부 확인 |

---

## 6. 설정 파일 구조

```
docker/monitoring/
├── otel-collector/
│   └── otel-collector-config.yml    # OTLP 수신 → Jaeger/Prometheus 내보내기
├── prometheus/
│   └── prometheus.yml               # scrape targets 정의
├── loki/
│   └── loki-config.yml              # 로그 저장 (7일 보존)
├── promtail/
│   └── promtail-config.yml          # Docker 로그 수집 → Loki 전송
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── datasources.yml      # Prometheus, Jaeger, Loki 자동 등록
│       └── dashboards/
│           └── dashboards.yml       # 대시보드 프로비저닝
└── mysqld-exporter/
    └── .my.cnf                      # MySQL 접속 정보
```

---

## 7. OpenTelemetry 계측

### 7.1 앱 계측 방식

`opentelemetry-instrument` CLI로 자동 계측 (코드 수정 없음):

```bash
# start_main.sh
opentelemetry-instrument \
    --service_name speedcam-api \
    gunicorn config.wsgi:application ...

# start_ocr_worker.sh
opentelemetry-instrument \
    --service_name speedcam-ocr \
    celery -A config worker ...

# start_alert_worker.sh
opentelemetry-instrument \
    --service_name speedcam-alert \
    celery -A config worker ...
```

### 7.2 자동 계측 대상

| 패키지 | 계측 대상 |
|--------|-----------|
| `opentelemetry-instrumentation-django` | HTTP 요청/응답, 미들웨어 |
| `opentelemetry-instrumentation-celery` | 태스크 실행, 큐 대기 시간 |
| `opentelemetry-instrumentation-pymysql` | DB 쿼리, 커넥션 |
| `opentelemetry-instrumentation-requests` | 외부 HTTP 호출 (GCS, FCM) |
| `opentelemetry-instrumentation-logging` | 로그에 trace_id/span_id 주입 |

### 7.3 환경변수 (backend.env)

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_RESOURCE_ATTRIBUTES=service.namespace=speedcam,deployment.environment=dev
OTEL_TRACES_SAMPLER=parentbased_tracealways
OTEL_PYTHON_LOG_CORRELATION=true
```

### 7.4 데이터 흐름

```
Django/Celery → (OTLP gRPC) → OTel Collector
                                  ├── traces → Jaeger
                                  └── metrics → Prometheus (:8889)

Django /metrics → (HTTP scrape) → Prometheus (django-prometheus 메트릭)
```

---

## 8. 로그 → 트레이스 연동 (Loki ↔ Jaeger)

### 8.1 동작 원리

1. `opentelemetry-instrumentation-logging`이 로그에 `trace_id`, `span_id` 주입
2. Django LOGGING 포맷:
   ```
   INFO 2024-01-01 12:00:00 views [trace_id=abc123 span_id=def456] Request processed
   ```
3. Promtail이 로그에서 `trace_id` 추출 → Loki 라벨로 저장
4. Grafana Loki 데이터소스의 `derivedFields`가 trace_id → Jaeger 링크 자동 생성

### 8.2 확인 방법

1. Grafana → Explore → Loki 데이터소스 선택
2. `{service="main"}` 쿼리 실행
3. 로그 라인의 `trace_id=` 부분 클릭 → Jaeger 트레이스로 이동

---

## 9. 유용한 PromQL 쿼리

### 9.1 Django

```promql
# 초당 요청 수 (RPS)
rate(django_http_requests_total_by_method_total[5m])

# 응답 시간 p95
histogram_quantile(0.95, rate(django_http_requests_latency_seconds_by_view_method_bucket[5m]))

# HTTP 5xx 에러율
rate(django_http_responses_total_by_status_total{status=~"5.."}[5m])
/ rate(django_http_responses_total_by_status_total[5m])

# DB 쿼리 수
rate(django_db_execute_total[5m])
```

### 9.2 RabbitMQ

```promql
# 큐별 대기 메시지 수
rabbitmq_queue_messages{queue=~"ocr_queue|fcm_queue"}

# 초당 메시지 발행율
rate(rabbitmq_queue_messages_published_total[5m])

# Consumer 수
rabbitmq_queue_consumers{queue=~"ocr_queue|fcm_queue"}
```

### 9.3 MySQL

```promql
# 활성 커넥션 수
mysql_global_status_threads_connected

# 초당 쿼리 수
rate(mysql_global_status_questions[5m])

# 슬로우 쿼리 수
rate(mysql_global_status_slow_queries[5m])
```

### 9.4 Celery

```promql
# 태스크 성공/실패 수
celery_tasks_total{state="SUCCESS"}
celery_tasks_total{state="FAILURE"}

# 태스크 실행 시간
celery_tasks_runtime_seconds{quantile="0.95"}

# 큐 길이
celery_queue_length
```

### 9.5 컨테이너 리소스

```promql
# 컨테이너별 CPU 사용률
rate(container_cpu_usage_seconds_total{name=~"speedcam-.*"}[5m]) * 100

# 컨테이너별 메모리 사용량 (MB)
container_memory_usage_bytes{name=~"speedcam-.*"} / 1024 / 1024

# 컨테이너별 네트워크 I/O (bytes/sec)
rate(container_network_receive_bytes_total{name=~"speedcam-.*"}[5m])
```

---

## 10. K6 부하 테스트 + 모니터링

### 10.1 실행

```bash
cd docker

# Smoke Test
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/smoke.js

# Load Test
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/load.js

# Stress Test
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/stress.js
```

### 10.2 K6 → Prometheus 메트릭

k6는 `--out experimental-prometheus-rw`로 결과를 Prometheus에 직접 기록. `--web.enable-remote-write-receiver` 플래그가 Prometheus에 설정되어 있음.

| k6 메트릭 | PromQL | 의미 |
|-----------|--------|------|
| `k6_http_req_duration_seconds` | `histogram_quantile(0.95, rate(k6_http_req_duration_seconds_bucket[1m]))` | HTTP p95 응답 시간 |
| `k6_http_reqs_total` | `rate(k6_http_reqs_total[1m])` | 초당 HTTP 요청 수 |
| `k6_vus` | `k6_vus` | 현재 VU 수 |
| `k6_http_req_failed_total` | `rate(k6_http_req_failed_total[1m])` | 실패율 |

### 10.3 부하 테스트 중 모니터링 체크리스트

부하 테스트 중 Grafana에서 아래 항목을 실시간 확인:

| 확인 항목 | 보는 곳 | 정상 기준 |
|-----------|---------|-----------|
| API 응답 시간 | Prometheus - django 메트릭 | p95 < 500ms |
| 에러율 | Prometheus - django 5xx rate | < 1% |
| RabbitMQ 큐 깊이 | Prometheus - rabbitmq 메트릭 | 지속 증가 없음 |
| Celery 태스크 처리율 | Prometheus - celery 메트릭 | 발행율 ≈ 소비율 |
| MySQL 커넥션 | Prometheus - mysql 메트릭 | < pool size 80% |
| 컨테이너 CPU/메모리 | Prometheus - cadvisor 메트릭 | CPU < 80%, Memory < 85% |
| 분산 트레이스 | Jaeger | 에러 트레이스 없음 |
| 로그 에러 | Loki | ERROR 로그 급증 없음 |

---

## 11. GCP 멀티 인스턴스 배포 시 고려사항

현재 Docker Compose는 단일 호스트 내 가상 네트워크. 인스턴스를 분리할 경우:

### 11.1 인스턴스 분리 구성 예시

| 인스턴스 | 서비스 | GCP 머신 타입 |
|----------|--------|---------------|
| app | main, flower | e2-medium |
| ocr-worker | ocr-worker | e2-standard-2 (CPU) |
| alert-worker | alert-worker | e2-small |
| db | mysql | e2-highmem-2 |
| mq | rabbitmq | e2-medium |
| monitoring | prometheus, grafana, jaeger, loki, promtail, otel-collector, cadvisor, exporters | e2-standard-2 |

### 11.2 네트워크 연결 방법

**방법 A: GCP 내부 IP 직접 지정**

```bash
# 각 인스턴스의 backend.env에서 컨테이너명 대신 내부 IP 사용
DB_HOST=10.178.0.11                                  # db 인스턴스
CELERY_BROKER_URL=amqp://sa:1234@10.178.0.12:5672//  # mq 인스턴스
OTEL_EXPORTER_OTLP_ENDPOINT=http://10.178.0.15:4317  # monitoring 인스턴스
```

**방법 B: GCP 내부 DNS (같은 VPC)**

```bash
DB_HOST=db-instance.asia-northeast3-a.c.PROJECT_ID.internal
```

**방법 C: GKE (Kubernetes) — 서비스 분리가 목적이면 추천**

- Service DNS 자동 부여: `mysql.default.svc.cluster.local`
- IP 관리 불필요
- HPA로 worker auto-scaling 가능
- `kompose convert`로 docker-compose → k8s 변환 가능

### 11.3 Prometheus 멀티 인스턴스 설정

인스턴스가 분리되면 `prometheus.yml`에서 내부 IP 사용:

```yaml
scrape_configs:
  - job_name: "django"
    static_configs:
      - targets: ["10.178.0.10:8000"]  # app 인스턴스

  - job_name: "rabbitmq"
    static_configs:
      - targets: ["10.178.0.12:15692"]  # mq 인스턴스

  - job_name: "mysql"
    static_configs:
      - targets: ["10.178.0.11:9104"]  # db 인스턴스 (mysqld-exporter 같이 띄움)

  - job_name: "celery"
    static_configs:
      - targets: ["10.178.0.13:9808"]  # celery-exporter를 어디서 띄울지 결정 필요
```

### 11.4 주의사항

- GCP 방화벽 규칙에서 모니터링 포트 (9090, 4317, 15692, 9104, 9808 등) 내부 허용 필요
- 외부 노출하면 안 되는 포트: Prometheus (9090), Grafana (3000) → VPN 또는 IAP 터널 사용
- 각 인스턴스에서 cAdvisor를 로컬로 띄우고, 모니터링 인스턴스의 Prometheus가 모든 cAdvisor를 scrape

---

## 12. 트러블슈팅

### 12.1 OTel Collector 연결 실패

```bash
docker logs speedcam-otel-collector
# "connection refused" → Jaeger 미기동 확인
# "context deadline exceeded" → 네트워크 문제
```

### 12.2 Grafana 데이터소스 연결 실패

```bash
# Grafana 컨테이너에서 직접 확인
docker exec speedcam-grafana curl -s http://prometheus:9090/-/healthy
docker exec speedcam-grafana curl -s http://loki:3100/ready
docker exec speedcam-grafana curl -s http://jaeger:16686/
```

### 12.3 Promtail 로그 수집 안됨

```bash
docker logs speedcam-promtail
# Docker socket 접근 권한 확인
# container name이 speedcam-* 패턴인지 확인
```

### 12.4 mysqld-exporter 인증 실패

```bash
docker logs speedcam-mysqld-exporter
# "Access denied" → .my.cnf의 user/password 확인
# "no configuration found" → config.my-cnf 마운트 경로 확인
```
