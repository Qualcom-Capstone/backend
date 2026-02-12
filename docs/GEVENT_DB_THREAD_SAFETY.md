# Django + Celery Gevent Pool: DB Thread-Safety 이슈 분석 및 해결

## STAR 분석

---

## 1. Situation (상황)

### 프로젝트 개요

SpeedCam 프로젝트는 과속 감지 시스템으로, 다음과 같은 MSA 아키텍처를 사용한다:

| 인스턴스 | 역할 | 핵심 기술 |
|----------|------|-----------|
| speedcam-app | Django + Gunicorn + MQTT Subscriber | HTTP API, MQTT 메시지 수신 |
| speedcam-db | MySQL 8.0 | 3개 DB (detections, vehicles, notifications) |
| speedcam-mq | RabbitMQ | 메시지 큐 (ocr_queue, fcm_queue) |
| speedcam-ocr | Celery OCR Worker | `--pool=prefork --concurrency=4` |
| speedcam-alert | Celery Alert Worker | `--pool=gevent --concurrency=100` |
| speedcam-mon | Prometheus + Grafana + Loki + Jaeger | 모니터링 |

### 문제 발생 지점

Jaeger 트레이싱에서 `send_notification` 태스크 실행 시 다음 에러가 반복적으로 발생:

```
DatabaseWrapper objects created in a thread can only be used in that same thread.
The object with alias 'detections_db' was created in thread id 35839779840
and this is thread id 35804459008.
```

> **📸 캡처 1**: Jaeger UI에서 `send_notification` span의 에러 로그
> - URL: `http://34.47.70.132:16686`
> - 검색 조건: Service=`speedcam-alert`, Operation=`send_notification`
> - 에러가 포함된 span을 클릭하여 상세 로그 확인
> - **캡처 항목**: span 타임라인 + Logs 탭의 에러 메시지 전문

### Alert Worker 실행 설정

```bash
# scripts/start_alert_worker.sh
opentelemetry-instrument \
    --service_name speedcam-alert \
    celery -A config worker \
    --pool=gevent \                    # ← gevent pool 사용
    --concurrency=${ALERT_CONCURRENCY:-100} \  # ← greenlet 100개
    --queues=fcm_queue \
    --hostname=alert@%h \
    --loglevel=${LOG_LEVEL:-info}
```

> **📸 캡처 2**: Alert Worker 컨테이너 시작 로그
> ```bash
> gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
>   -- sudo docker logs speedcam-alert 2>&1 | head -20
> ```
> - **캡처 항목**: `celery@alert` 워커 시작 메시지에서 pool=gevent, concurrency=100 확인

### Django DB 설정 (CONN_MAX_AGE 미설정)

```python
# config/settings/prod.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "speedcam",
        # ... (CONN_MAX_AGE 미설정 → 기본값 0)
    },
    "vehicles_db": { ... },      # CONN_MAX_AGE 미설정
    "detections_db": { ... },    # CONN_MAX_AGE 미설정
    "notifications_db": { ... }, # CONN_MAX_AGE 미설정
}
```

### 문제의 태스크 코드

```python
# tasks/notification_tasks.py
@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),   # ← 모든 예외에 대해 자동 재시도
    retry_backoff=True,
    acks_late=True,
)
def send_notification(self, detection_id: int):
    from apps.detections.models import Detection
    # ...
    detection = Detection.objects.using("detections_db").get(  # ← line 36: 에러 발생 지점
        id=detection_id, status="completed"
    )
```

이 태스크는 3개의 DB에 접근한다:
- `detections_db`: Detection 조회 (line 36)
- `notifications_db`: Notification 생성 (line 59, 89, 129, 145, 168)
- `vehicles_db`: Vehicle 조회 (line 109)

---

## 2. Task (과제)

### 해결해야 할 문제

1. **즉각적 문제**: `send_notification` 태스크가 gevent greenlet 환경에서 DB 커넥션 스레드 공유 에러로 실패
2. **근본 원인 파악**: Django ORM의 스레드 안전성 모델과 gevent greenlet 간의 충돌 메커니즘 규명
3. **안정적 해결**: 프로덕션 환경에서 100 concurrency gevent pool이 안정적으로 DB 접근하도록 수정

### 성공 기준

- [ ] Jaeger에서 `send_notification` span에 `DatabaseWrapper` 에러 없음
- [ ] Alert Worker의 100 concurrent greenlet이 안정적으로 동작
- [ ] 기존 OCR Worker(prefork pool)에 부정적 영향 없음

---

## 3. Action (분석 및 조치)

### 3-1. 근본 원인 분석

#### 원인 Layer 1: Gevent Monkey-Patching 순서 문제 (Late Patching)

Alert Worker 시작 로그에서 다음 경고들이 확인된다:

```
# 실제 speedcam-alert 컨테이너 시작 로그
MonkeyPatchWarning: Monkey-patching ssl after ssl has already been imported
may lead to errors, including RecursionError on Python 3.6. It may also
silently lead to incorrect behaviour on Python 3.7.
Please monkey-patch earlier. See https://github.com/gevent/gevent/issues/1016.
Modules that had direct imports (NOT patched):
  ['urllib3.util.ssl_ (...)', 'urllib3.util (...)']
```

```
Exception ignored in: <function _after_fork_in_child at 0x71500038ea20>
  File "gevent/threading.py", line 264, in _after_fork_in_child
    assert len(active) == 1
           ^^^^^^^^^^^^^^^^
AssertionError
```

> **📸 캡처 2-1**: Alert Worker 컨테이너 시작 로그 (경고 메시지 포함)
> ```bash
> gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
>   -- sudo docker logs speedcam-alert 2>&1 | head -20
> ```
> - **캡처 항목**: `MonkeyPatchWarning`과 `AssertionError` 전문

**이 경고가 발생하는 이유:**

`start_alert_worker.sh`의 실행 체인:

```
opentelemetry-instrument → celery -A config worker --pool=gevent
```

```
실행 순서 (시간순):
1. opentelemetry-instrument 시작
   → urllib3 import → ssl import됨 (이미 native ssl 모듈 로드)
2. celery -A config worker --pool=gevent 실행
3. Celery가 --pool=gevent 감지
   → gevent.monkey.patch_all() 호출  ← 💥 ssl은 이미 import됨!
4. ssl, 일부 threading 모듈이 불완전하게 패치된 상태로 동작
```

**영향:**
- `_thread.get_ident()`는 패치되어 greenlet ID를 반환하지만
- `threading.local()`의 일부 동작이 불완전할 수 있음
- `_after_fork_in_child`에서 active 스레드 수가 예상과 다름 (AssertionError)
- **결과**: greenlet 간 DB 커넥션 격리가 불안정해져 `validate_thread_sharing()` 에러 발생 확률 증가

> **참고**: gevent 공식 문서는 monkey-patching을 "프로그램 생명주기에서 가능한 한 빨리, 다른 import보다 먼저" 수행하라고 권고한다.
> 그러나 `opentelemetry-instrument` 래퍼가 먼저 실행되므로 현재 구조에서는 이를 완전히 제어하기 어렵다.

#### 원인 Layer 2: Django의 DB 커넥션 스레드 격리 메커니즘

Django는 `django/db/backends/base/base.py`의 `validate_thread_sharing()` 메서드로 DB 커넥션의 스레드 간 공유를 차단한다:

```python
# django/db/backends/base/base.py (Django 소스코드)
def validate_thread_sharing(self):
    if not (self.allow_thread_sharing or self._thread_ident == _thread.get_ident()):
        raise DatabaseError(
            "DatabaseWrapper objects created in a "
            "thread can only be used in that same thread. The object "
            "with alias '%s' was created in thread id %s and this is "
            "thread id %s." % (self.alias, self._thread_ident, _thread.get_ident())
        )
```

> **📸 캡처 3**: Django 소스코드에서 `validate_thread_sharing()` 확인
> ```bash
> # Django 패키지 내 소스 위치 확인
> gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
>   -- sudo docker exec speedcam-alert python -c "
> import django.db.backends.base.base as b
> import inspect
> print(inspect.getsource(b.BaseDatabaseWrapper.validate_thread_sharing))"
> ```
> - **캡처 항목**: 실제 배포된 Django 버전의 `validate_thread_sharing()` 소스코드 출력

#### 원인 Layer 3: Greenlet ≠ Thread이지만 다른 Thread ID를 가짐

```
[일반 스레드 모델]
Thread A (id=100) → DB Connection A (thread_ident=100) → ✅ 같은 ID

[Gevent Greenlet 모델]
Greenlet A (id=200) → DB Connection 생성 (thread_ident=200)
    ↓ (예외 발생 → autoretry)
Greenlet B (id=300) → DB Connection 재사용 시도 (thread_ident=200) → ❌ ID 불일치!
```

gevent가 `monkey.patch_all()`을 실행하면:
1. `threading.local()`이 greenlet-local로 패치됨
2. `_thread.get_ident()`가 greenlet ID를 반환하도록 패치됨
3. 각 greenlet은 고유한 "스레드 ID"를 가지게 됨

#### 원인 Layer 4: `autoretry_for=(Exception,)`이 문제를 악화시키는가

```
Timeline:
  t=0  Greenlet-A (id=200): send_notification(42) 시작
  t=1  Greenlet-A (id=200): DB connection 생성 (thread_ident=200)
  t=2  Greenlet-A (id=200): Detection.objects.get() → 예외 발생
  t=3  [Celery autoretry] 태스크를 재시도 큐에 넣음
  t=4  Greenlet-B (id=300): send_notification(42) 재시도 시작  ← 다른 greenlet!
  t=5  Greenlet-B (id=300): 기존 connection 접근 시도
                            → thread_ident(200) ≠ current_ident(300) → 💥 에러!
```

> **📸 캡처 4**: Jaeger에서 retry span 확인
> - URL: `http://34.47.70.132:16686`
> - `send_notification` 트레이스에서 retry가 발생한 span을 찾아 원본과 retry의 span 관계 확인
> - **캡처 항목**: 원본 span → retry span 으로 이어지는 트레이스 타임라인

#### OCR Worker는 왜 이 문제가 없는가

| 설정 | Alert Worker | OCR Worker |
|------|-------------|------------|
| Pool | `gevent` (greenlet) | `prefork` (프로세스) |
| Concurrency | 100 | 4 |
| 동시성 단위 | greenlet (같은 프로세스, 다른 "스레드" ID) | 별도 프로세스 (fork 후 새 커넥션) |
| `_thread.get_ident()` | greenlet마다 다름 | 프로세스마다 독립 |
| DB 커넥션 | greenlet 간 공유 위험 | 프로세스 격리로 안전 |

#### 원인 계층 요약

```
Layer 1: Late Monkey-Patching (opentelemetry-instrument → ssl 먼저 import)
    ↓ 불완전한 threading 패치
Layer 2: Django validate_thread_sharing() 스레드 격리 검증
    ↓ _thread.get_ident()로 커넥션 소유자 확인
Layer 3: Greenlet마다 다른 Thread ID
    ↓ greenlet-local 저장소에 커넥션 바인딩
Layer 4: autoretry_for=(Exception,) 자동 재시도
    ↓ 다른 greenlet에서 재시도 → stale 커넥션 접근
    💥 DatabaseWrapper thread-sharing error
```

### 3-2. 해결 방안 비교

| 방안 | 설명 | 장점 | 단점 | 채택 |
|------|------|------|------|------|
| **A. `close_old_connections()` 호출** | 태스크 시작 시 기존 커넥션 닫기 | 간단, 비침습적 | 매 태스크마다 새 커넥션 오버헤드 | ✅ |
| **B. Celery Signal 사용** | `task_prerun`/`task_postrun` signal로 일괄 처리 | 태스크 코드 수정 없음 | 전역 영향, 디버깅 난이도 | ⚠️ 대안 |
| **C. `CONN_MAX_AGE = 0` 설정** | 매 요청마다 커넥션 닫기 | Django 표준 방식 | Celery에서는 "요청" 개념 없음, 불충분 | ❌ |
| **D. `inc_thread_sharing()` 사용** | 스레드 공유 허용 플래그 | 에러 해소 | race condition 위험, 비권장 | ❌ |
| **E. gevent → prefork 전환** | Pool 타입 변경 | 근본 해결 | I/O 집약 태스크에 비효율적 | ❌ |
| **F. OTel 래퍼 제거 후 코드 내 초기화** | monkey.patch_all()을 앱 진입점에서 먼저 호출 | Late patching 해소 | OTel 자동 계측 포기 | ⚠️ 장기 검토 |

### 3-3. 채택한 해결 방안: `db.close_old_connections()`

#### 수정 전 (현재 코드)

```python
# tasks/notification_tasks.py
@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), ...)
def send_notification(self, detection_id: int):
    from apps.detections.models import Detection
    from apps.notifications.models import Notification
    from apps.vehicles.models import Vehicle

    try:
        detection = Detection.objects.using("detections_db").get(...)  # ← 💥 에러 발생 가능
```

#### 수정 후 (적용 예정)

```python
# tasks/notification_tasks.py
from django import db  # ← 추가

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), ...)
def send_notification(self, detection_id: int):
    # Gevent greenlet 환경에서 스레드 간 DB 커넥션 공유 방지
    db.close_old_connections()  # ← 추가: 이전 greenlet의 stale 커넥션 정리

    from apps.detections.models import Detection
    from apps.notifications.models import Notification
    from apps.vehicles.models import Vehicle

    try:
        detection = Detection.objects.using("detections_db").get(...)  # ← ✅ 새 커넥션 사용
```

#### `db.close_old_connections()`의 동작 원리

```python
# django/db/__init__.py
def close_old_connections(**kwargs):
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()
```

이 함수는:
1. 모든 DB alias(`default`, `detections_db`, `vehicles_db`, `notifications_db`)를 순회
2. 각 커넥션이 **사용 불가능(unusable)**하거나 **수명 초과(obsolete)**인지 확인
3. 해당되면 커넥션을 닫음 → 다음 ORM 호출 시 새 커넥션 자동 생성

greenlet 환경에서 이 함수가 효과적인 이유:
- 이전 greenlet이 남긴 stale 커넥션을 정리
- 현재 greenlet에서 새 커넥션이 생성되므로 `_thread_ident`가 현재 greenlet ID와 일치

### 3-4. 유사 사례: Java Virtual Thread

이 문제는 Python/Django에만 국한되지 않는다. Java의 Virtual Thread(Project Loom)에서도 유사한 범주의 문제가 발생할 수 있다:

| 항목 | Python Gevent Greenlet | Java Virtual Thread |
|------|----------------------|---------------------|
| ThreadLocal 동작 | greenlet-local로 패치됨 | 가상 스레드마다 고유 ThreadLocal |
| DB 커넥션 관리 | Django의 thread-local 저장 | 보통 HikariCP 같은 글로벌 풀 사용 |
| 핵심 문제 | **thread ID 불일치로 validation 실패** | **Connection pinning** (carrier thread 고갈) |
| 프레임워크 차단 | Django가 명시적 validate | 명시적 차단 없음, 암묵적 race condition |

**공통 근본 원인**: 경량 동시성 단위(greenlet/virtual thread)가 thread-local 스토리지 패턴과 충돌

---

## 4. Result (결과)

### 4-1. 수정 적용 전 상태 (Before)

> **📸 캡처 5**: 수정 전 Jaeger 에러 확인
> - URL: `http://34.47.70.132:16686`
> - Service: `speedcam-alert`, Lookback: Last Hour
> - **캡처 항목**: `send_notification` 트레이스 목록에서 에러(빨간색) 표시된 span들

> **📸 캡처 6**: 수정 전 Grafana Logs Explorer
> - URL: `http://34.47.70.132:3000` → Logs Explorer 대시보드
> - Container: `speedcam-alert` 선택
> - Search: `DatabaseWrapper`
> - **캡처 항목**: "DatabaseWrapper objects created in a thread" 에러 로그 라인들

> **📸 캡처 7**: 수정 전 Alert Worker 컨테이너 로그
> ```bash
> gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
>   -- sudo docker logs speedcam-alert 2>&1 | grep -i "DatabaseWrapper" | tail -10
> ```
> - **캡처 항목**: 터미널에서 grep한 DatabaseWrapper 에러 로그

### 4-2. 수정 적용 후 상태 (After)

> **📸 캡처 8**: 수정 후 코드 diff 확인
> ```bash
> git diff docs/gevent-db-thread-safety -- tasks/notification_tasks.py
> ```
> - **캡처 항목**: `db.close_old_connections()` 추가된 diff 출력

> **📸 캡처 9**: 수정 후 Alert Worker 재배포 확인
> ```bash
> gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
>   -- sudo docker compose -f ~/depoly/compose/docker-compose.alert.yml up -d --build
> ```
> - **캡처 항목**: 컨테이너 재시작 로그

> **📸 캡처 10**: 수정 후 Jaeger 정상 트레이스
> - URL: `http://34.47.70.132:16686`
> - Service: `speedcam-alert`
> - **캡처 항목**: `send_notification` 트레이스에 에러 없는 정상 span들 (수정 후 시점부터)

> **📸 캡처 11**: 수정 후 Grafana Logs Explorer
> - Container: `speedcam-alert`, Search: `DatabaseWrapper`
> - **캡처 항목**: 수정 후 시점부터 DatabaseWrapper 에러 로그 없음

### 4-3. 영향 분석

| 항목 | Before | After |
|------|--------|-------|
| `send_notification` 에러율 | DatabaseWrapper 에러 반복 발생 | 에러 제거 |
| DB 커넥션 패턴 | stale 커넥션 재사용 시도 → 실패 | 매 태스크 시작 시 정리 → 새 커넥션 |
| OCR Worker 영향 | - | 없음 (prefork pool이므로 해당 없음) |
| 성능 오버헤드 | - | 미미 (커넥션 정리는 O(n) where n=DB alias 수=4) |

---

## 참고 자료 (References)

### 공식 문서

| 출처 | 링크 | 내용 |
|------|------|------|
| Django Databases | https://docs.djangoproject.com/en/5.1/ref/databases/ | CONN_MAX_AGE, 스레드 안전성, persistent connections |
| Celery Gevent Pool | https://docs.celeryq.dev/en/main/userguide/concurrency/gevent.html | gevent pool 공식 가이드 |
| Celery Workers Guide | https://docs.celeryq.dev/en/stable/userguide/workers.html | Worker 구성 및 pool 타입 |
| Gevent Monkey Patching | http://www.gevent.org/api/gevent.monkey.html | monkey patch API 레퍼런스 |

### Django 소스코드

| 파일 | 내용 |
|------|------|
| `django/db/backends/base/base.py` | `validate_thread_sharing()` 구현 |
| `django/db/__init__.py` | `close_old_connections()` 구현 |
| [Django PR #10972](https://github.com/django/django/pull/10972) | Thread sharing 로직 개선 |
| [Django Ticket #30171](https://code.djangoproject.com/ticket/30171) | Threading 에러 수정 |
| [Django Ticket #25714](https://code.djangoproject.com/ticket/25714) | DatabaseWrapper 스레드 에러 |

### GitHub Issues (동일 문제 보고)

| 이슈 | 내용 |
|------|------|
| [Gunicorn #879](https://github.com/benoitc/gunicorn/issues/879) | Gunicorn + Django + Gevent에서 동일 에러 |
| [Celery #4489](https://github.com/celery/celery/issues/4489) | Celery에서 DatabaseWrapper 스레드 에러 |
| [Celery #2453](https://github.com/celery/celery/issues/2453) | Celery가 DB 커넥션을 닫지 않는 문제 |
| [Celery #5924](https://github.com/celery/celery/issues/5924) | Django + eventlet 패치 깨짐 |
| [Celery #3520](https://github.com/celery/celery/issues/3520) | Prefork에서 스레드 에러 |

### 기술 블로그 및 아티클

| 출처 | 링크 | 내용 |
|------|------|------|
| Celery School | https://celery.school/celery-gevent-5-lessons-learned | Gevent Pool 5가지 교훈 |
| DoorDash Engineering | https://doordash.engineering/2021/01/19/scaling-efficienc-of-a-python-service-with-gevent/ | 프로덕션 gevent 확장 사례 |
| Medium (Celery Workers) | https://medium.com/@gupta.rishabh2912/mastering-celery-workers-in-django-when-to-use-prefork-eventlet-or-gevent-2679cffae2bd | Pool 타입 비교 가이드 |
| Vinta Software | https://www.vintasoftware.com/blog/guide-django-celery-tasks | Django Celery 고급 가이드 |
| LimeChat | https://limechat.ai/blog/scaling-django-server-celery-workers | Django + Celery 스케일링 전략 |
| Heroku | https://devcenter.heroku.com/articles/python-concurrency-and-database-connections | Python 동시성 + DB 커넥션 best practices |

---

## 부록

### A. 확인 명령어 모음

```bash
# 1. Alert Worker 로그에서 에러 확인
gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
  -- sudo docker logs speedcam-alert 2>&1 | grep -i "DatabaseWrapper"

# 2. Jaeger에서 에러 트레이스 API 조회
curl -s "http://34.47.70.132:16686/api/traces?service=speedcam-alert&operation=send_notification&limit=20" \
  | python3 -m json.tool | grep -A2 "error"

# 3. Django validate_thread_sharing 소스 확인
gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
  -- sudo docker exec speedcam-alert python -c "
import django.db.backends.base.base as b
import inspect
print(inspect.getsource(b.BaseDatabaseWrapper.validate_thread_sharing))"

# 4. 현재 greenlet 수 확인 (gevent pool 상태)
gcloud compute ssh speedcam-alert --zone=asia-northeast3-a \
  -- sudo docker exec speedcam-alert python -c "
import gevent
print(f'Current greenlet count: {len(gevent.hub.get_hub().loop._callbacks)}')"

# 5. MySQL 커넥션 수 확인
gcloud compute ssh speedcam-db --zone=asia-northeast3-a \
  -- sudo docker exec speedcam-mysql mysql -usa -p'<password>' \
     -e "SHOW STATUS LIKE 'Threads_connected';"
```

### B. 관련 프로젝트 파일 경로

| 파일 | 역할 |
|------|------|
| `tasks/notification_tasks.py` | 알림 전송 태스크 (문제 발생 지점) |
| `tasks/ocr_tasks.py` | OCR 처리 태스크 (prefork pool, 참고용) |
| `scripts/start_alert_worker.sh` | Alert Worker 시작 스크립트 |
| `scripts/start_ocr_worker.sh` | OCR Worker 시작 스크립트 |
| `config/settings/prod.py` | 프로덕션 DB 설정 (CONN_MAX_AGE 미설정) |
| `config/settings/base.py` | Celery 공통 설정 |
