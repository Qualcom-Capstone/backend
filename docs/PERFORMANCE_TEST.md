# 성능 테스트 가이드

## 1. 개요

### 1.1 목적
Edge Device(Raspberry Pi) 없이 시스템의 성능과 안정성을 검증하기 위한 부하 테스트 수행

### 1.2 테스트 도구
- **K6**: 부하 테스트 도구
- **xk6-mqtt**: K6 MQTT 확장 (Edge Device 시뮬레이션)
- **Docker**: 테스트 환경 구성

### 1.3 테스트 대상
| 구간 | 설명 |
|------|------|
| MQTT → Main Service | Edge Device 메시지 수신 처리 |
| Main Service → RabbitMQ | Task 발행 성능 |
| OCR Worker | 이미지 처리 처리량 |
| Alert Worker | FCM 전송 처리량 |
| REST API | API 응답 시간 |

---

## 2. 테스트 환경 구성

### 2.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Performance Test Environment                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐         ┌─────────────────────────────────┐   │
│  │   K6 Runner     │         │     Application Stack           │   │
│  │                 │         │                                 │   │
│  │ - MQTT Publish  │ ──────▶ │  RabbitMQ (MQTT + AMQP)        │   │
│  │ - HTTP Request  │         │  Main Service (Django)          │   │
│  │ - Metrics       │ ──────▶ │  OCR Worker (Mock)             │   │
│  │                 │         │  Alert Worker (Mock)            │   │
│  └─────────────────┘         │  MySQL                          │   │
│                              └─────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────┐         ┌─────────────────────────────────┐   │
│  │   Monitoring    │         │     Mock Services               │   │
│  │                 │         │                                 │   │
│  │ - Grafana       │◀────────│  - GCS Mock (MinIO)            │   │
│  │ - Prometheus    │         │  - FCM Mock (WireMock)          │   │
│  │                 │         │                                 │   │
│  └─────────────────┘         └─────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Docker Compose (테스트 환경)

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  # 애플리케이션 스택
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: speedcam_test
      MYSQL_USER: sa
      MYSQL_PASSWORD: "1234"
    ports:
      - "3306:3306"
    networks:
      - test-network

  rabbitmq:
    image: rabbitmq:3.13-management
    environment:
      RABBITMQ_DEFAULT_USER: sa
      RABBITMQ_DEFAULT_PASS: "1234"
    ports:
      - "5672:5672"
      - "1883:1883"
      - "15672:15672"
    volumes:
      - ./rabbitmq/enabled_plugins:/etc/rabbitmq/enabled_plugins
      - ./rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf
    networks:
      - test-network

  main:
    build:
      context: ..
      dockerfile: docker/Dockerfile.main
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
    ports:
      - "8000:8000"
    depends_on:
      - mysql
      - rabbitmq
    networks:
      - test-network

  ocr-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.ocr
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - GCS_MOCK_URL=http://minio:9000
      - OCR_MOCK=true  # OCR Mock 모드
    depends_on:
      - rabbitmq
      - minio
    networks:
      - test-network

  alert-worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.alert
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - DB_HOST=mysql
      - DB_USER=sa
      - DB_PASSWORD=1234
      - CELERY_BROKER_URL=amqp://sa:1234@rabbitmq:5672//
      - FCM_MOCK_URL=http://wiremock:8080
    depends_on:
      - rabbitmq
      - wiremock
    networks:
      - test-network

  # Mock Services
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    networks:
      - test-network

  wiremock:
    image: wiremock/wiremock:3.3.1
    ports:
      - "8080:8080"
    volumes:
      - ./wiremock:/home/wiremock
    networks:
      - test-network

  # K6 Runner (Prometheus remote write로 결과 전송)
  k6:
    image: grafana/k6:latest
    volumes:
      - ./k6:/scripts
    environment:
      K6_PROMETHEUS_RW_SERVER_URL: http://prometheus:9090/api/v1/write
      K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM: "true"
      MAIN_SERVICE_URL: http://main:8000
      MQTT_BROKER: tcp://rabbitmq:1883
      MQTT_USER: sa
      MQTT_PASS: "1234"
    networks:
      - test-network
    depends_on:
      - main

networks:
  test-network:
    driver: bridge
```

### 2.3 Mock 서비스 설정

#### WireMock (FCM Mock)

**wiremock/mappings/fcm-send.json**
```json
{
  "request": {
    "method": "POST",
    "urlPattern": "/v1/projects/.*/messages:send"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "name": "projects/test/messages/{{randomValue type='UUID'}}"
    },
    "transformers": ["response-template"],
    "fixedDelayMilliseconds": 50
  }
}
```

#### OCR Mock 모드

```python
# tasks/ocr_tasks.py (테스트 모드)
import os
import random
import string

OCR_MOCK = os.getenv('OCR_MOCK', 'false').lower() == 'true'

def mock_ocr_result():
    """테스트용 가짜 OCR 결과 생성"""
    num1 = random.randint(10, 999)
    char = random.choice('가나다라마바사아자차카타파하')
    num2 = random.randint(1000, 9999)
    plate = f"{num1}{char}{num2}"
    confidence = random.uniform(0.85, 0.99)
    return plate, confidence

@shared_task(bind=True, max_retries=3, acks_late=True)
def process_ocr(self, detection_id: int, gcs_uri: str):
    try:
        Detection.objects.filter(id=detection_id).update(
            status='processing'
        )
        
        if OCR_MOCK:
            # Mock 모드: 실제 OCR 없이 가짜 결과 반환
            import time
            time.sleep(random.uniform(0.1, 0.5))  # 처리 시간 시뮬레이션
            plate_number, confidence = mock_ocr_result()
        else:
            # 실제 OCR 처리
            # ... 기존 코드 ...
            pass
        
        # 이하 동일
```

---

## 3. K6 설치 및 MQTT 확장

### 3.1 xk6-mqtt 빌드

MQTT 테스트를 위해 K6에 xk6-mqtt 확장을 추가합니다.

```bash
# xk6 설치
go install go.k6.io/xk6/cmd/xk6@latest

# xk6-mqtt 확장 포함하여 K6 빌드
xk6 build --with github.com/pmalhaire/xk6-mqtt@latest

# 빌드된 바이너리 확인
./k6 version
```

### 3.2 Docker 이미지 빌드

**k6/Dockerfile**
```dockerfile
FROM golang:1.21 as builder

RUN go install go.k6.io/xk6/cmd/xk6@latest

RUN xk6 build \
    --with github.com/pmalhaire/xk6-mqtt@latest \
    --output /k6

FROM grafana/k6:latest
COPY --from=builder /k6 /usr/bin/k6
```

---

## 4. 테스트 시나리오

### 4.1 테스트 유형

| 테스트 | 목적 | VU | Duration | 특징 |
|--------|------|-----|----------|------|
| **Smoke** | 기본 동작 확인 | 1-5 | 1분 | 최소 부하로 시스템 정상 동작 확인 |
| **Load** | 예상 부하 검증 | 50-100 | 10분 | 일반적인 운영 환경 시뮬레이션 |
| **Stress** | 시스템 한계 확인 | 100-500 | 30분 | 점진적 부하 증가로 Breaking Point 탐색 |
| **Spike** | 급증 대응력 확인 | 10→500→10 | 10분 | 급격한 트래픽 변화 대응 |
| **Soak** | 장시간 안정성 | 100 | 2-4시간 | 메모리 누수, 리소스 고갈 확인 |

### 4.2 예상 트래픽 기준

| 항목 | 값 | 설명 |
|------|-----|------|
| Edge Device 수 | 100대 | 동시 연결 카메라 수 |
| 이벤트/분/디바이스 | 10건 | 분당 과속 감지 이벤트 |
| 총 이벤트/분 | 1,000건 | 피크 시간대 |
| 총 이벤트/초 | ~17건 | 평균 TPS |

---

## 5. K6 테스트 스크립트

### 5.1 공통 설정

**k6/common/config.js**
```javascript
// 환경 변수 또는 기본값
export const CONFIG = {
  // 서비스 URL
  MAIN_SERVICE_URL: __ENV.MAIN_SERVICE_URL || 'http://main:8000',
  
  // MQTT 설정
  MQTT_BROKER: __ENV.MQTT_BROKER || 'tcp://rabbitmq:1883',
  MQTT_USER: __ENV.MQTT_USER || 'sa',
  MQTT_PASS: __ENV.MQTT_PASS || '1234',
  MQTT_TOPIC: 'detections/new',
  
  // 테스트 데이터
  CAMERAS: ['cam_001', 'cam_002', 'cam_003', 'cam_004', 'cam_005'],
  LOCATIONS: [
    '서울시 강남구 테헤란로',
    '서울시 서초구 반포대로',
    '서울시 송파구 올림픽로',
    '경기도 성남시 분당구',
    '인천시 연수구 센트럴로',
  ],
};

// 테스트용 Detection 메시지 생성
export function generateDetectionMessage() {
  const camera = CONFIG.CAMERAS[Math.floor(Math.random() * CONFIG.CAMERAS.length)];
  const location = CONFIG.LOCATIONS[Math.floor(Math.random() * CONFIG.LOCATIONS.length)];
  const speedLimit = [50, 60, 80, 100][Math.floor(Math.random() * 4)];
  const detectedSpeed = speedLimit + Math.random() * 40 + 10; // 제한속도 + 10~50
  
  return JSON.stringify({
    camera_id: camera,
    location: location,
    detected_speed: Math.round(detectedSpeed * 10) / 10,
    speed_limit: speedLimit,
    detected_at: new Date().toISOString(),
    image_gcs_uri: `gs://test-bucket/${camera}/${Date.now()}.jpg`,
  });
}

// 성능 임계값 (Thresholds)
export const THRESHOLDS = {
  // HTTP 요청
  http_req_duration: ['p(95)<500', 'p(99)<1000'],
  http_req_failed: ['rate<0.01'],
  
  // MQTT 발행
  mqtt_publish_duration: ['p(95)<100'],
  mqtt_publish_failed: ['rate<0.01'],
  
  // 커스텀 메트릭
  detection_e2e_duration: ['p(95)<30000'], // End-to-End 30초 이내
};
```

### 5.2 Smoke Test

**k6/tests/smoke.js**
```javascript
import mqtt from 'k6/x/mqtt';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { CONFIG, generateDetectionMessage, THRESHOLDS } from '../common/config.js';

// 커스텀 메트릭
const mqttPublishDuration = new Trend('mqtt_publish_duration');
const mqttPublishFailed = new Counter('mqtt_publish_failed');

export const options = {
  vus: 3,
  duration: '1m',
  thresholds: THRESHOLDS,
};

// MQTT 클라이언트 (VU당 1개)
const client = new mqtt.Client(
  CONFIG.MQTT_BROKER,
  `k6-smoke-${__VU}-${Date.now()}`
);

export function setup() {
  // API 헬스체크
  const res = http.get(`${CONFIG.MAIN_SERVICE_URL}/health/`);
  check(res, {
    'API is healthy': (r) => r.status === 200,
  });
  
  console.log('Smoke Test 시작: 기본 동작 확인');
}

export default function () {
  // MQTT 연결
  client.connect({
    username: CONFIG.MQTT_USER,
    password: CONFIG.MQTT_PASS,
  });
  
  // Detection 메시지 발행
  const message = generateDetectionMessage();
  const startTime = Date.now();
  
  try {
    client.publish(CONFIG.MQTT_TOPIC, message, 1, false);
    mqttPublishDuration.add(Date.now() - startTime);
    
    check(null, {
      'MQTT publish successful': () => true,
    });
  } catch (e) {
    mqttPublishFailed.add(1);
    console.error(`MQTT publish failed: ${e}`);
  }
  
  client.disconnect();
  
  // API 조회 테스트
  const apiRes = http.get(`${CONFIG.MAIN_SERVICE_URL}/api/v1/detections/pending/`);
  check(apiRes, {
    'API status 200': (r) => r.status === 200,
    'API response time < 500ms': (r) => r.timings.duration < 500,
  });
  
  sleep(1);
}

export function teardown() {
  console.log('Smoke Test 완료');
}
```

### 5.3 Load Test

**k6/tests/load.js**
```javascript
import mqtt from 'k6/x/mqtt';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend, Rate } from 'k6/metrics';
import { CONFIG, generateDetectionMessage, THRESHOLDS } from '../common/config.js';

// 커스텀 메트릭
const mqttPublishDuration = new Trend('mqtt_publish_duration');
const mqttPublishFailed = new Counter('mqtt_publish_failed');
const detectionCreated = new Counter('detection_created');

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp-up
    { duration: '8m', target: 50 },   // Steady state
    { duration: '1m', target: 0 },    // Ramp-down
  ],
  thresholds: {
    ...THRESHOLDS,
    'detection_created': ['count>400'], // 10분간 최소 400건
  },
};

let client;

export function setup() {
  console.log('Load Test 시작: 예상 부하 검증');
  console.log(`Target: 50 VUs, 예상 TPS: ~17/s`);
}

export default function () {
  // VU별 MQTT 클라이언트 생성
  if (!client) {
    client = new mqtt.Client(
      CONFIG.MQTT_BROKER,
      `k6-load-${__VU}-${Date.now()}`
    );
  }
  
  client.connect({
    username: CONFIG.MQTT_USER,
    password: CONFIG.MQTT_PASS,
  });
  
  // 1. MQTT 메시지 발행 (Edge Device 시뮬레이션)
  const message = generateDetectionMessage();
  const startTime = Date.now();
  
  try {
    client.publish(CONFIG.MQTT_TOPIC, message, 1, false);
    mqttPublishDuration.add(Date.now() - startTime);
    detectionCreated.add(1);
    
    check(null, { 'MQTT publish OK': () => true });
  } catch (e) {
    mqttPublishFailed.add(1);
  }
  
  client.disconnect();
  
  // 2. API 부하 (프론트엔드 시뮬레이션)
  const endpoints = [
    '/api/v1/detections/',
    '/api/v1/detections/pending/',
    '/api/v1/detections/statistics/',
  ];
  
  const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
  const apiRes = http.get(`${CONFIG.MAIN_SERVICE_URL}${endpoint}`);
  
  check(apiRes, {
    'API status 200': (r) => r.status === 200,
    'API response < 500ms': (r) => r.timings.duration < 500,
  });
  
  // 초당 약 17건 (50 VU * 0.33건/VU/초)
  sleep(3);
}

export function teardown() {
  console.log('Load Test 완료');
}
```

### 5.4 Stress Test

**k6/tests/stress.js**
```javascript
import mqtt from 'k6/x/mqtt';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend, Gauge } from 'k6/metrics';
import { CONFIG, generateDetectionMessage, THRESHOLDS } from '../common/config.js';

// 커스텀 메트릭
const mqttPublishDuration = new Trend('mqtt_publish_duration');
const mqttPublishFailed = new Counter('mqtt_publish_failed');
const activeVUs = new Gauge('active_vus');
const queueDepth = new Gauge('estimated_queue_depth');

export const options = {
  stages: [
    // 점진적 부하 증가
    { duration: '2m', target: 50 },
    { duration: '5m', target: 50 },
    { duration: '2m', target: 100 },
    { duration: '5m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '5m', target: 200 },
    { duration: '2m', target: 300 },
    { duration: '5m', target: 300 },
    // Breaking point 탐색
    { duration: '2m', target: 500 },
    { duration: '5m', target: 500 },
    // Ramp-down
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // Stress 시 완화
    http_req_failed: ['rate<0.1'],       // 10% 미만 실패 허용
    mqtt_publish_failed: ['rate<0.05'],  // 5% 미만 실패 허용
  },
};

let client;

export function setup() {
  console.log('Stress Test 시작: 시스템 한계 확인');
  console.log('단계: 50 → 100 → 200 → 300 → 500 VUs');
}

export default function () {
  activeVUs.add(__VU);
  
  if (!client) {
    client = new mqtt.Client(
      CONFIG.MQTT_BROKER,
      `k6-stress-${__VU}-${Date.now()}`
    );
  }
  
  try {
    client.connect({
      username: CONFIG.MQTT_USER,
      password: CONFIG.MQTT_PASS,
    });
    
    const message = generateDetectionMessage();
    const startTime = Date.now();
    
    client.publish(CONFIG.MQTT_TOPIC, message, 1, false);
    mqttPublishDuration.add(Date.now() - startTime);
    
    client.disconnect();
  } catch (e) {
    mqttPublishFailed.add(1);
    console.error(`Stress error at VU ${__VU}: ${e}`);
  }
  
  // API 부하
  const apiRes = http.get(`${CONFIG.MAIN_SERVICE_URL}/api/v1/detections/`);
  check(apiRes, {
    'API responds': (r) => r.status === 200 || r.status === 503,
  });
  
  // RabbitMQ Queue 깊이 확인 (추정)
  try {
    const rmqRes = http.get(
      'http://rabbitmq:15672/api/queues/%2F/ocr_queue',
      { auth: 'sa:1234' }
    );
    if (rmqRes.status === 200) {
      const queue = JSON.parse(rmqRes.body);
      queueDepth.add(queue.messages || 0);
    }
  } catch (e) {
    // Queue 모니터링 실패 무시
  }
  
  sleep(1);
}

export function teardown() {
  console.log('Stress Test 완료');
  console.log('Breaking Point 분석 필요');
}
```

### 5.5 Spike Test

**k6/tests/spike.js**
```javascript
import mqtt from 'k6/x/mqtt';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { CONFIG, generateDetectionMessage } from '../common/config.js';

const mqttPublishDuration = new Trend('mqtt_publish_duration');
const mqttPublishFailed = new Counter('mqtt_publish_failed');
const recoveryTime = new Trend('recovery_time');

export const options = {
  stages: [
    // 정상 상태
    { duration: '1m', target: 10 },
    // 급격한 스파이크
    { duration: '10s', target: 500 },
    // 스파이크 유지
    { duration: '1m', target: 500 },
    // 급격한 감소
    { duration: '10s', target: 10 },
    // 정상 상태 복귀
    { duration: '2m', target: 10 },
    // 두 번째 스파이크
    { duration: '10s', target: 300 },
    { duration: '1m', target: 300 },
    { duration: '10s', target: 10 },
    // 복구 확인
    { duration: '2m', target: 10 },
    // 종료
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],  // Spike 시 완화된 임계값
    mqtt_publish_failed: ['rate<0.1'],   // 10% 미만 실패 허용
  },
};

let client;
let preSpikeDuration = null;

export function setup() {
  console.log('Spike Test 시작: 급격한 트래픽 변화 대응력 확인');
  console.log('시나리오: 10 → 500 → 10 → 300 → 10 VUs');
}

export default function () {
  if (!client) {
    client = new mqtt.Client(
      CONFIG.MQTT_BROKER,
      `k6-spike-${__VU}-${Date.now()}`
    );
  }
  
  try {
    client.connect({
      username: CONFIG.MQTT_USER,
      password: CONFIG.MQTT_PASS,
    });
    
    const message = generateDetectionMessage();
    const startTime = Date.now();
    
    client.publish(CONFIG.MQTT_TOPIC, message, 1, false);
    const duration = Date.now() - startTime;
    mqttPublishDuration.add(duration);
    
    // 스파이크 전 기준 응답 시간 저장
    if (__ITER < 60 && !preSpikeDuration) {
      preSpikeDuration = duration;
    }
    
    // 복구 시간 측정 (스파이크 후 정상 응답으로 돌아오는 시간)
    if (__ITER > 200 && preSpikeDuration) {
      if (duration <= preSpikeDuration * 1.5) {
        recoveryTime.add(__ITER);
      }
    }
    
    client.disconnect();
  } catch (e) {
    mqttPublishFailed.add(1);
  }
  
  // API 응답 확인
  const apiRes = http.get(`${CONFIG.MAIN_SERVICE_URL}/api/v1/detections/pending/`);
  check(apiRes, {
    'API responds during spike': (r) => r.status === 200 || r.status === 503,
  });
  
  sleep(0.5);
}

export function teardown() {
  console.log('Spike Test 완료');
  console.log('복구 시간 분석 필요');
}
```

### 5.6 Soak Test

**k6/tests/soak.js**
```javascript
import mqtt from 'k6/x/mqtt';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend, Gauge } from 'k6/metrics';
import { CONFIG, generateDetectionMessage } from '../common/config.js';

const mqttPublishDuration = new Trend('mqtt_publish_duration');
const mqttPublishFailed = new Counter('mqtt_publish_failed');
const memoryUsage = new Gauge('memory_usage_estimate');
const dbConnections = new Gauge('db_connections_estimate');

export const options = {
  stages: [
    { duration: '5m', target: 100 },   // Ramp-up
    { duration: '4h', target: 100 },   // 4시간 유지 (조정 가능: 2h, 8h)
    { duration: '5m', target: 0 },     // Ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    mqtt_publish_failed: ['rate<0.01'],
  },
};

let client;
let iterationCount = 0;

export function setup() {
  console.log('Soak Test 시작: 장시간 안정성 확인');
  console.log('Duration: 4시간, VUs: 100');
  console.log('확인 항목: 메모리 누수, DB 커넥션 풀 고갈, 성능 저하');
}

export default function () {
  iterationCount++;
  
  if (!client) {
    client = new mqtt.Client(
      CONFIG.MQTT_BROKER,
      `k6-soak-${__VU}-${Date.now()}`
    );
  }
  
  try {
    client.connect({
      username: CONFIG.MQTT_USER,
      password: CONFIG.MQTT_PASS,
    });
    
    const message = generateDetectionMessage();
    const startTime = Date.now();
    
    client.publish(CONFIG.MQTT_TOPIC, message, 1, false);
    mqttPublishDuration.add(Date.now() - startTime);
    
    client.disconnect();
  } catch (e) {
    mqttPublishFailed.add(1);
  }
  
  // API 호출
  const apiRes = http.get(`${CONFIG.MAIN_SERVICE_URL}/api/v1/detections/`);
  check(apiRes, {
    'API status 200': (r) => r.status === 200,
    'API response < 500ms': (r) => r.timings.duration < 500,
  });
  
  // 주기적으로 시스템 상태 확인 (10분마다)
  if (iterationCount % 600 === 0) {
    console.log(`Checkpoint at iteration ${iterationCount}`);
    
    // Health check
    const healthRes = http.get(`${CONFIG.MAIN_SERVICE_URL}/health/`);
    if (healthRes.status !== 200) {
      console.error('Health check failed!');
    }
    
    // RabbitMQ Queue 상태
    try {
      const rmqRes = http.get(
        'http://rabbitmq:15672/api/overview',
        { auth: 'sa:1234' }
      );
      if (rmqRes.status === 200) {
        const overview = JSON.parse(rmqRes.body);
        console.log(`RabbitMQ Messages: ${overview.queue_totals?.messages || 0}`);
      }
    } catch (e) {
      // 무시
    }
  }
  
  sleep(1);
}

export function teardown() {
  console.log('Soak Test 완료');
  console.log(`Total iterations: ${iterationCount}`);
  console.log('메모리 사용량 그래프 및 성능 추이 분석 필요');
}
```

---

## 6. 테스트 실행 방법

### 6.1 테스트 환경 시작

```bash
# 1. 테스트 환경 시작
cd docs
docker compose -f docker-compose.test.yml up -d

# 2. 서비스 준비 대기
sleep 30

# 3. 헬스체크
curl http://localhost:8000/health/
```

### 6.2 K6 테스트 실행

```bash
# 기본: 별도 테스트 환경 (docker-compose.test.yml)
docker compose -f docker-compose.test.yml run k6 run --out experimental-prometheus-rw /scripts/tests/smoke.js

# 또는: 실제 환경 + 모니터링 스택 사용
cd docker
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/smoke.js

# Load Test (10분)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/load.js

# Stress Test (37분)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/stress.js

# Spike Test (9분)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/spike.js

# Soak Test (4시간+)
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  run k6 run --out experimental-prometheus-rw /scripts/tests/soak.js
```

### 6.3 결과 확인

- **Grafana Dashboard**: http://localhost:3000 (admin/admin)
- **Prometheus Targets**: http://localhost:9090/targets (모든 타겟 UP 확인)
- **Jaeger Tracing**: http://localhost:16686 (분산 트레이스)
- **RabbitMQ Management**: http://localhost:15672 (sa/1234)
- **Flower (Celery)**: http://localhost:5555

### 6.4 K6 결과를 Prometheus에서 확인

K6는 `--out experimental-prometheus-rw`로 결과를 Prometheus에 직접 기록합니다.

```promql
# 초당 요청 수
rate(k6_http_reqs_total[1m])

# p95 응답 시간
histogram_quantile(0.95, rate(k6_http_req_duration_seconds_bucket[1m]))

# 현재 VU 수
k6_vus

# 에러율
rate(k6_http_req_failed_total[1m])
```

부하 테스트 중 Grafana에서 실시간 모니터링 가능 — 상세 PromQL은 `docs/MONITORING.md` 참조.

---

## 7. 메트릭 및 분석

### 7.1 핵심 메트릭

| 메트릭 | 설명 | 목표값 |
|--------|------|--------|
| `http_req_duration` (p95) | API 응답 시간 | < 500ms |
| `mqtt_publish_duration` (p95) | MQTT 발행 시간 | < 100ms |
| `http_req_failed` | API 실패율 | < 1% |
| `mqtt_publish_failed` | MQTT 발행 실패율 | < 1% |
| `detection_e2e_duration` | 감지→알림 전체 시간 | < 30초 |

### 7.2 RabbitMQ 메트릭

| 메트릭 | 설명 | 경고 임계값 |
|--------|------|-------------|
| Queue Depth (ocr_queue) | OCR 대기 메시지 수 | > 1000 |
| Queue Depth (fcm_queue) | FCM 대기 메시지 수 | > 500 |
| Consumer Count | 활성 Consumer 수 | = 0 (장애) |
| Message Rate | 초당 메시지 처리량 | 감소 추세 |

### 7.3 시스템 메트릭

| 메트릭 | 설명 | 경고 임계값 |
|--------|------|-------------|
| CPU Usage | CPU 사용률 | > 80% |
| Memory Usage | 메모리 사용률 | > 85% |
| DB Connections | DB 커넥션 수 | > Pool Size 80% |
| Network I/O | 네트워크 트래픽 | 급격한 변화 |

### 7.4 Grafana Dashboard JSON

Grafana에서 Prometheus 데이터소스로 K6 대시보드를 구성합니다.

**주요 패널 PromQL 쿼리:**

| 패널 | PromQL |
|------|--------|
| Virtual Users | `k6_vus` |
| HTTP p95 Duration | `histogram_quantile(0.95, rate(k6_http_req_duration_seconds_bucket[30s]))` |
| Requests/sec | `rate(k6_http_reqs_total[30s])` |
| Error Rate | `rate(k6_http_req_failed_total[30s]) / rate(k6_http_reqs_total[30s])` |
| MQTT Publish Duration | `rate(k6_mqtt_publish_duration_sum[30s]) / rate(k6_mqtt_publish_duration_count[30s])` |

또는 Grafana 공식 K6 대시보드 (ID: `19665`)를 import하여 사용할 수 있습니다.
Grafana → Dashboards → Import → Dashboard ID `19665` 입력

---

## 8. 테스트 결과 분석 체크리스트

### 8.1 Smoke Test
- [ ] 모든 컴포넌트 정상 동작
- [ ] MQTT → Django → RabbitMQ 흐름 확인
- [ ] API 응답 정상

### 8.2 Load Test
- [ ] 목표 TPS 달성 (17건/초)
- [ ] p95 응답 시간 < 500ms
- [ ] 에러율 < 1%
- [ ] Queue 백로그 축적 없음

### 8.3 Stress Test
- [ ] Breaking Point 식별 (VU 수, TPS)
- [ ] 장애 발생 지점 확인
- [ ] 리소스 병목 구간 확인 (CPU/Memory/DB/Queue)
- [ ] 장애 시 Graceful Degradation 여부

### 8.4 Spike Test
- [ ] 스파이크 시 시스템 다운 없음
- [ ] 복구 시간 측정
- [ ] 메시지 유실 여부 확인
- [ ] Auto-scaling 동작 확인 (적용 시)

### 8.5 Soak Test
- [ ] 메모리 누수 없음 (일정한 메모리 사용량)
- [ ] DB 커넥션 풀 안정
- [ ] 성능 저하 없음 (시간 경과에 따른 응답 시간)
- [ ] 로그 파일 사이즈 관리

---

## 9. 트러블슈팅

### 9.1 일반적인 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| MQTT 연결 실패 | RabbitMQ MQTT Plugin 미활성화 | `rabbitmq-plugins enable rabbitmq_mqtt` |
| Queue 백로그 증가 | Worker 처리량 부족 | Worker concurrency 증가 |
| DB 커넥션 고갈 | Pool Size 부족 | `CONN_MAX_AGE`, `pool_size` 증가 |
| OOM Kill | 메모리 부족 | Container 메모리 제한 증가 |

### 9.2 성능 병목 해결

```bash
# RabbitMQ Queue 상태 확인
curl -u sa:1234 http://localhost:15672/api/queues/%2F/ocr_queue

# MySQL 커넥션 상태 확인
mysql -u sa -p1234 -e "SHOW PROCESSLIST;"

# Celery Worker 상태 확인
celery -A config inspect active

# Docker 리소스 사용량
docker stats
```

---

## 10. 권장 테스트 순서

```
1. Smoke Test (1분)
   └─ 기본 동작 확인
   
2. Load Test (10분)
   └─ 예상 부하 검증
   
3. Stress Test (37분)
   └─ 시스템 한계 확인
   
4. Spike Test (9분)
   └─ 급증 대응력 확인
   
5. Soak Test (4시간)
   └─ 장시간 안정성 확인
```

각 테스트 후 결과를 분석하고, 발견된 문제를 해결한 후 다음 테스트를 진행합니다.

