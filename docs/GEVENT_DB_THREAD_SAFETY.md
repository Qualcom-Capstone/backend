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

<!-- 📸 캡처 1: Jaeger에서 send_notification 에러 span
     - http://34.47.70.132:16686 → Service: speedcam-alert, Operation: send_notification
     - 에러 span 클릭 → Logs 탭의 에러 메시지 전문 -->

같은 프로젝트의 OCR 워커(`--pool=prefork --concurrency=4`)는 멀쩡했다. Alert 워커만 터지고 있었다.

---

## Task — 왜 greenlet에서만 터지는가

에러 메시지를 곧이곧대로 읽으면 "스레드 A가 만든 DB 커넥션을 스레드 B가 쓰려 했다"는 뜻이다. 그런데 gevent는 스레드가 아니라 greenlet을 쓴다. 문제를 풀려면 세 가지를 이해해야 했다:

1. Django가 DB 커넥션을 어떻게 격리하는지
2. gevent monkey-patching이 그 격리를 어떻게 무너뜨리는지
3. Celery의 autoretry가 왜 상황을 악화시키는지

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

커넥션이 생성될 때의 `_thread.get_ident()` 값을 `_thread_ident`에 저장해두고, 쿼리 실행 시점의 ID와 비교한다. 다르면 즉시 예외를 던진다.

일반적인 멀티스레드 환경에서는 당연히 잘 동작한다. 각 스레드는 고유한 ID를 가지고, `threading.local()`이 스레드별 커넥션을 격리하니까.

### 2단계: gevent가 바꿔놓은 규칙

gevent의 `monkey.patch_all()`은 `_thread.get_ident()`를 패치해서 **greenlet ID를 반환**하도록 바꾼다. 즉, greenlet마다 다른 "스레드 ID"를 갖게 된다.

```
[일반 스레드]
Thread A (id=100) → DB Connection (thread_ident=100) → 쿼리 시 get_ident()=100 ✅

[Gevent Greenlet]
Greenlet A (id=200) → DB Connection (thread_ident=200)
    ↓ 예외 발생 → autoretry
Greenlet B (id=300) → 같은 Connection 접근 → get_ident()=300 ≠ 200 ❌
```

여기서 `autoretry_for=(Exception,)` 설정이 문제를 악화시킨다. Celery의 자동 재시도는 태스크를 큐에 다시 넣고, **다른 greenlet이 그것을 집어간다.** 이전 greenlet이 남긴 DB 커넥션에 새 greenlet이 접근하는 순간 Django의 검증에 걸린다.

<!-- 📸 캡처 2: Jaeger에서 retry span 관계 확인
     - send_notification 트레이스에서 원본 span → retry span 이어지는 타임라인 -->

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

<!-- 📸 캡처 3: Alert Worker 시작 로그
     - docker logs speedcam-alert 2>&1 | head -20
     - MonkeyPatchWarning과 AssertionError가 보이는 구간 -->

원인은 실행 순서다:

```
1. opentelemetry-instrument 시작 → urllib3 → ssl import됨
2. celery worker --pool=gevent 실행
3. Celery가 gevent.monkey.patch_all() 호출 ← ssl은 이미 로드된 상태
```

gevent 공식 문서는 monkey-patching을 "가능한 한 빨리, 다른 import보다 먼저" 하라고 권고한다. 하지만 `opentelemetry-instrument` 래퍼가 먼저 실행되면서 패치 순서가 꼬인다. 이로 인해 threading 관련 패치가 불완전해지고, greenlet 간 DB 커넥션 격리가 더 불안정해진다.

### 4단계: 왜 OCR Worker는 괜찮은가

| | Alert Worker | OCR Worker |
|---|---|---|
| Pool | `gevent` (greenlet) | `prefork` (프로세스) |
| Concurrency | 100 | 4 |
| 커넥션 격리 | greenlet 간 공유 위험 | 프로세스 격리로 안전 |

prefork는 `fork()`로 별도 프로세스를 만든다. 프로세스마다 독립적인 메모리 공간을 가지므로 커넥션 공유 자체가 불가능하다. gevent만의 문제다.

### 원인 요약

```
opentelemetry-instrument가 ssl을 먼저 import
    → gevent monkey-patching이 불완전하게 적용
        → greenlet마다 다른 thread ID 부여
            → autoretry 시 다른 greenlet이 태스크를 받음
                → 이전 greenlet의 DB 커넥션에 접근
                    → Django validate_thread_sharing() 실패
                        💥 DatabaseWrapper thread-sharing error
```

### 해결: `db.close_old_connections()`

검토한 방안들:

| 방안 | 판단 |
|------|------|
| **`db.close_old_connections()` 호출** | ✅ 채택 — 간단하고 비침습적 |
| Celery Signal(`task_prerun`) 사용 | ⚠️ 대안 — 태스크 코드 수정 없이 전역 적용 가능하나 디버깅 어려움 |
| `CONN_MAX_AGE = 0` 설정 | ❌ — Celery에는 "요청" 개념이 없어 작동하지 않음 |
| `inc_thread_sharing()` | ❌ — race condition 위험, Django가 비권장 |
| gevent → prefork 전환 | ❌ — I/O 집약 태스크에서 비효율적 |
| OTel 래퍼 제거 후 코드 내 monkey-patch | ⚠️ 장기 검토 — late patching 근본 해결이나 자동 계측 포기 |

수정은 단순하다. 태스크 시작 시 stale 커넥션을 정리하면 된다:

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
    db.close_old_connections()  # stale 커넥션 정리 → 새 커넥션으로 시작

    from apps.detections.models import Detection
    # ...
    detection = Detection.objects.using("detections_db").get(...)  # ✅
```

`close_old_connections()`는 모든 DB alias를 순회하며 사용 불가능하거나 수명이 초과된 커넥션을 닫는다. 이후 ORM 호출 시 현재 greenlet에서 새 커넥션이 생성되므로 `_thread_ident`가 일치하게 된다.

<!-- 📸 캡처 4: 수정 코드 diff
     - git diff -- tasks/notification_tasks.py -->

---

## Result — Before & After

<!-- 📸 캡처 5: [Before] Jaeger 에러 트레이스 목록
     - http://34.47.70.132:16686 → Service: speedcam-alert
     - send_notification 에러(빨간색) span들이 보이는 목록 -->

<!-- 📸 캡처 6: [Before] Grafana Logs Explorer
     - http://34.47.70.132:3000 → Logs Explorer
     - Container: speedcam-alert, Search: DatabaseWrapper -->

<!-- 📸 캡처 7: [After] Jaeger 정상 트레이스
     - 수정 배포 후 send_notification 에러 없는 정상 span들 -->

<!-- 📸 캡처 8: [After] Grafana Logs Explorer
     - 수정 후 DatabaseWrapper 에러 로그 없음 확인 -->

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
