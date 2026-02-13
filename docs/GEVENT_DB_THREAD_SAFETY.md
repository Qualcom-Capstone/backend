# Celery Gevent Pool에서 Django DB 커넥션이 깨지는 이유

> Celery의 gevent pool과 Django ORM을 함께 쓸 때 마주치는 `DatabaseWrapper objects created in a thread can only be used in that same thread` 에러의 원인과 해결.

---

## Situation — 어느 날 Jaeger에서 발견한 에러

과속 감지 시스템의 알림 워커(Alert Worker)는 FCM 푸시 전송처럼 I/O 집약적인 작업을 처리한다. 네트워크 대기가 대부분이라 `--pool=gevent --concurrency=100`으로 greenlet 100개를 띄워 처리량을 극대화했다.

```bash
# scripts/start_alert_worker.sh
opentelemetry-instrument \
    --service_name speedcam-alert \
    celery -A config worker \
    --pool=gevent \
    --concurrency=${ALERT_CONCURRENCY:-100} \
    --queues=fcm_queue \
    --hostname=alert@%h
```

문제는 Jaeger 트레이싱을 확인하면서 드러났다. `send_notification` 태스크에서 이런 에러가 반복되고 있었다:

```
DatabaseWrapper objects created in a thread can only be used in that same thread.
The object with alias 'detections_db' was created in thread id 35839779840
and this is thread id 35804459008.
```

> **📸 캡처 1**: Jaeger에서 `send_notification` 에러 span
> - `http://34.47.70.132:16686` → Service: `speedcam-alert`, Operation: `send_notification`
> - 에러 span 클릭 → Logs 탭의 에러 메시지 전문

같은 프로젝트의 OCR 워커(`--pool=prefork --concurrency=4`)는 멀쩡했다. Alert 워커만 터지고 있었다.

```mermaid
graph LR
    subgraph "정상: OCR Worker (prefork)"
        P1[Process A] -->|독립 커넥션| DB1[(MySQL)]
        P2[Process B] -->|독립 커넥션| DB1
    end
    subgraph "문제: Alert Worker (gevent)"
        G1[Greenlet A] -.->|stale 커넥션 공유| DB2[(MySQL)]
        G2[Greenlet B] -.->|💥 thread ID 불일치| DB2
    end
    style G2 fill:#ff6b6b,color:#fff
```

---

## Task — 왜 greenlet에서만 터지는가

에러 메시지를 곧이곧대로 읽으면 "스레드 A가 만든 DB 커넥션을 스레드 B가 쓰려 했다"는 뜻이다. 그런데 gevent는 스레드가 아니라 greenlet을 쓴다. 문제를 풀려면 세 가지를 이해해야 했다:

1. Django가 DB 커넥션을 어떻게 격리하는지
2. gevent monkey-patching이 그 격리를 어떻게 무너뜨리는지
3. Celery의 autoretry가 왜 상황을 악화시키는지

솔직히 말하면 이 문제를 처음 마주했을 때 꽤 당황스러웠다. 나는 주로 Spring 기반으로 개발해왔기 때문에 HikariCP 같은 글로벌 커넥션 풀에 익숙했고, 런타임에 표준 라이브러리를 통째로 바꿔치는 monkey-patching이라는 개념 자체가 낯설었다. Spring에서는 Virtual Thread를 써도 커넥션 풀이 스레드와 무관하게 동작하는데, Django는 커넥션을 스레드에 바인딩한다. 이 차이를 이해하는 과정이 오히려 두 프레임워크의 동시성 모델을 더 깊이 비교할 수 있는 계기가 되었다.

---

## Action — 원인 추적과 해결

### 1단계: Django의 스레드 격리 검증

Django는 모든 DB 쿼리 실행 전에 `validate_thread_sharing()`을 호출한다:

```python
# django/db/backends/base/base.py
def validate_thread_sharing(self):
    if not (self.allow_thread_sharing
            or self._thread_ident == _thread.get_ident()):
        raise DatabaseError(
            "DatabaseWrapper objects created in a thread can only "
            "be used in that same thread."
        )
```

커넥션이 생성될 때의 `_thread.get_ident()` 값을 저장해두고, 쿼리 실행 시점의 ID와 비교한다. 다르면 즉시 예외를 던진다. 일반적인 멀티스레드 환경에서는 당연히 잘 동작한다. 각 스레드는 고유한 ID를 가지고, `threading.local()`이 스레드별 커넥션을 격리하니까.

### 2단계: gevent가 바꿔놓은 규칙

gevent의 `monkey.patch_all()`은 `_thread.get_ident()`를 패치해서 **greenlet ID를 반환**하도록 바꾼다. 즉 greenlet마다 다른 "스레드 ID"를 갖게 된다.

```mermaid
sequenceDiagram
    participant Q as RabbitMQ (fcm_queue)
    participant GA as Greenlet A (id=200)
    participant GB as Greenlet B (id=300)
    participant DB as MySQL (detections_db)

    Q->>GA: send_notification(42) 배정
    GA->>DB: Connection 생성 (thread_ident=200)
    GA->>DB: Detection.objects.get() 쿼리
    DB-->>GA: ❌ 예외 발생
    Note over GA: autoretry_for=(Exception,)<br/>→ 태스크를 큐에 재등록

    GA->>Q: 재시도 요청
    Q->>GB: send_notification(42) 재배정
    GB->>DB: 기존 Connection 접근 시도<br/>thread_ident=200 ≠ get_ident()=300
    Note over GB,DB: 💥 DatabaseWrapper<br/>thread-sharing error
```

여기서 `autoretry_for=(Exception,)` 설정이 문제를 악화시킨다. Celery의 자동 재시도는 태스크를 큐에 다시 넣고, **다른 greenlet이 그것을 집어간다.** 이전 greenlet이 남긴 DB 커넥션에 새 greenlet이 접근하는 순간 Django의 검증에 걸린다.

> **📸 캡처 2**: Jaeger에서 retry span 관계 확인
> - `send_notification` 트레이스에서 원본 span → retry span 이어지는 타임라인

### 3단계: Late Monkey-Patching이라는 복병

워커 시작 로그를 보면 또 다른 단서가 있었다:

```
MonkeyPatchWarning: Monkey-patching ssl after ssl has already been imported
may lead to errors. Please monkey-patch earlier.
See https://github.com/gevent/gevent/issues/1016.
```

```
Exception ignored in: <function _after_fork_in_child at 0x71500038ea20>
  File "gevent/threading.py", line 264, in _after_fork_in_child
    assert len(active) == 1
AssertionError
```

> **📸 캡처 3**: Alert Worker 시작 로그
> - `docker logs speedcam-alert 2>&1 | head -20`
> - `MonkeyPatchWarning`과 `AssertionError`가 보이는 구간

원인은 실행 순서다:

```mermaid
flowchart LR
    A["opentelemetry-instrument<br/>시작"] --> B["urllib3 import<br/>→ ssl 로드됨"]
    B --> C["celery worker<br/>--pool=gevent"]
    C --> D["gevent.monkey<br/>.patch_all()"]
    D --> E["⚠️ ssl은<br/>이미 import됨"]
    style E fill:#ff6b6b,color:#fff
```

gevent 공식 문서는 monkey-patching을 "가능한 한 빨리, 다른 import보다 먼저" 하라고 권고한다. 하지만 `opentelemetry-instrument` 래퍼가 먼저 실행되면서 패치 순서가 꼬인다. 이로 인해 threading 관련 패치가 불완전해지고, greenlet 간 DB 커넥션 격리가 더 불안정해진다.

### 원인 요약

```mermaid
flowchart TB
    L1["Layer 1: Late Monkey-Patching<br/>opentelemetry-instrument → ssl 먼저 import"]
    L2["Layer 2: Django validate_thread_sharing()<br/>_thread.get_ident()로 커넥션 소유자 확인"]
    L3["Layer 3: Greenlet별 다른 Thread ID<br/>monkey-patch가 greenlet ID를 반환"]
    L4["Layer 4: autoretry<br/>다른 greenlet이 재시도 태스크를 받음"]
    ERR["💥 DatabaseWrapper thread-sharing error"]

    L1 -->|불완전한 threading 패치| L2
    L2 -->|스레드 격리 검증| L3
    L3 -->|stale 커넥션 접근| L4
    L4 --> ERR

    style L1 fill:#ffeaa7
    style ERR fill:#ff6b6b,color:#fff
```

### 해결: Trade-off를 따져보다

원인을 파악했으니 해결 방안을 검토했다. 핵심은 **"어떤 비용을 감수할 것인가"**였다.

**방안 A. `db.close_old_connections()` — 태스크 시작 시 호출**

매 태스크가 실행될 때마다 모든 DB alias의 stale 커넥션을 닫는다. 다음 ORM 호출 시 현재 greenlet에서 새 커넥션이 생성된다.
- *Trade-off*: 매번 커넥션을 새로 맺는 오버헤드가 발생한다. 하지만 Alert Worker의 태스크는 FCM 전송(네트워크 I/O)이 병목이므로 DB 커넥션 생성 비용(~1ms)은 무시할 수 있는 수준이다.

**방안 B. Celery Signal(`task_prerun`) — 전역 훅**

```python
@signals.task_prerun.connect
def close_db_connections(**kwargs):
    close_old_connections()
```

태스크 코드를 수정하지 않아도 되지만, 모든 태스크에 전역으로 적용된다. 문제는 OCR Worker처럼 이 이슈가 없는 워커에도 불필요하게 커넥션을 닫게 된다는 점이다. 그리고 Signal은 암묵적으로 동작하기 때문에 나중에 "왜 커넥션이 자꾸 끊기지?"라는 디버깅 지옥에 빠질 수 있다.
- *Trade-off*: 코드 수정 없음 vs. 전역 부작용 + 디버깅 난이도

**방안 C. `CONN_MAX_AGE = 0` 설정**

Django의 표준적인 커넥션 수명 관리. 하지만 이 설정은 **요청-응답 사이클이 끝날 때** 커넥션을 닫는 방식이다. Celery 태스크에는 "요청"이라는 개념이 없으므로 아예 트리거되지 않는다.
- *Trade-off*: 해당 없음 — 동작하지 않음

**방안 D. `inc_thread_sharing()` — 스레드 공유 허용**

Django가 제공하는 escape hatch. 커넥션의 스레드 검증을 끈다. 에러는 사라지지만, 여러 greenlet이 같은 커넥션을 동시에 사용할 수 있게 되어 race condition 위험이 생긴다. Django 공식 문서도 이 방식을 권장하지 않는다.
- *Trade-off*: 에러 해소 vs. 데이터 정합성 위험

**방안 E. gevent → prefork 전환**

근본적으로 gevent를 쓰지 않으면 문제 자체가 없다. 하지만 Alert Worker는 FCM 푸시라는 I/O 바운드 작업에 특화되어 있고, prefork의 프로세스 기반 모델은 동시 100개 처리에 메모리 비효율적이다.
- *Trade-off*: 문제 근본 해결 vs. I/O 집약 워크로드에 부적합

**방안 F. OTel 래퍼 제거 후 코드 내 monkey-patch**

Late patching의 근본 원인을 해결할 수 있다. 하지만 `opentelemetry-instrument`가 제공하는 자동 계측(auto-instrumentation)을 포기해야 한다. 직접 계측 코드를 작성해야 하며, 유지보수 부담이 생긴다.
- *Trade-off*: late patching 해소 vs. OTel 자동 계측 포기

**결론: 방안 A를 채택했다.**

```mermaid
quadrantChart
    title 해결 방안 Trade-off 비교
    x-axis 낮은 침습성 --> 높은 침습성
    y-axis 낮은 안정성 --> 높은 안정성
    A. close_old_connections: [0.25, 0.78]
    B. Celery Signal: [0.2, 0.6]
    D. inc_thread_sharing: [0.35, 0.2]
    E. prefork 전환: [0.85, 0.9]
    F. OTel 래퍼 제거: [0.75, 0.75]
```

가장 실용적인 선택이다. 코드 변경이 한 줄이고, 영향 범위가 해당 태스크로 한정되며, 커넥션 재생성 비용은 FCM 네트워크 I/O 대비 무시할 수 있다. "왜 이 코드가 있는지"도 주석 한 줄이면 충분하다.

**수정 전:**
```python
@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), ...)
def send_notification(self, detection_id: int):
    from apps.detections.models import Detection
    # ...
    detection = Detection.objects.using("detections_db").get(...)  # 💥
```

**수정 후:**
```python
from django import db

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), ...)
def send_notification(self, detection_id: int):
    db.close_old_connections()  # gevent greenlet 간 stale 커넥션 정리

    from apps.detections.models import Detection
    # ...
    detection = Detection.objects.using("detections_db").get(...)  # ✅
```

`close_old_connections()`는 모든 DB alias를 순회하며 사용 불가능하거나 수명이 초과된 커넥션을 닫는다. 이후 ORM 호출 시 현재 greenlet에서 새 커넥션이 생성되므로 `_thread_ident`가 일치하게 된다.

> **📸 캡처 4**: 수정 코드 diff
> - `git diff -- tasks/notification_tasks.py`

---

## Result — Before & After

> **📸 캡처 5**: [Before] Jaeger 에러 트레이스 목록
> - `http://34.47.70.132:16686` → Service: `speedcam-alert`
> - `send_notification` 에러(빨간색) span들이 보이는 목록

> **📸 캡처 6**: [Before] Grafana Logs Explorer
> - `http://34.47.70.132:3000` → Logs Explorer
> - Container: `speedcam-alert`, Search: `DatabaseWrapper`

> **📸 캡처 7**: [After] Jaeger 정상 트레이스
> - 수정 배포 후 `send_notification` 에러 없는 정상 span들

> **📸 캡처 8**: [After] Grafana Logs Explorer
> - 수정 후 `DatabaseWrapper` 에러 로그 없음 확인

| | Before | After |
|---|---|---|
| `send_notification` 에러율 | DatabaseWrapper 에러 반복 | 에러 제거 |
| DB 커넥션 패턴 | stale 커넥션 재사용 → 실패 | 태스크 시작 시 정리 → 새 커넥션 |
| OCR Worker 영향 | — | 없음 (prefork pool) |
| 성능 오버헤드 | — | 미미 (DB alias 4개 순회) |

---

## References

### 공식 문서

- [Django Databases — Persistent connections and thread safety](https://docs.djangoproject.com/en/5.1/ref/databases/#persistent-database-connections)
- [Celery — Concurrency with Gevent](https://docs.celeryq.dev/en/stable/userguide/concurrency/gevent.html)
- [Gevent — Monkey Patching](http://www.gevent.org/api/gevent.monkey.html)

### GitHub Issues

- [Celery #4489](https://github.com/celery/celery/issues/4489) — Workers inherit DatabaseWrapper during fork, thread ID mismatch
- [Celery #2453](https://github.com/celery/celery/issues/2453) — Celery not closing database connections properly
- [Gunicorn #879](https://github.com/benoitc/gunicorn/issues/879) — DatabaseWrapper thread error with gevent worker

### 기술 블로그

- [DoorDash Engineering — Scaling Efficiency of a Python Service with Gevent](https://doordash.engineering/2021/01/19/scaling-efficienc-of-a-python-service-with-gevent/)
- [Heroku — Python Concurrency and Database Connections](https://devcenter.heroku.com/articles/python-concurrency-and-database-connections)
- [Celery School — The Gevent Pool: 5 Lessons Learned](https://celery.school/celery-gevent-5-lessons-learned)
