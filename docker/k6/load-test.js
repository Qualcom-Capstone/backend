import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import exec from 'k6/execution';

// ============================================================
// SpeedCam v2 부하테스트 - Event Driven Architecture (비동기 OCR)
// ============================================================
// 인프라: 8x GCP 인스턴스 (기존 6 + OCR Worker 2대 추가)
//   - speedcam-app (10.178.0.4): Django + Gunicorn + MQTT Subscriber (e2-small)
//   - speedcam-db (10.178.0.2): MySQL 8.0 (e2-medium)
//   - speedcam-mq (10.178.0.7): RabbitMQ MQTT + AMQP (e2-small)
//   - speedcam-ocr (10.178.0.3): Celery OCR Worker (e2-small, concurrency=1)
//   - speedcam-ocr-2 (10.178.0.11): Celery OCR Worker (e2-medium, concurrency=2) [신규]
//   - speedcam-ocr-3 (10.178.0.10): Celery OCR Worker (e2-medium, concurrency=2) [신규]
//   - speedcam-alert (10.178.0.6): Kombu Consumer + Celery gevent Worker (e2-small)
//   - speedcam-mon (10.178.0.5): Prometheus + Grafana + Loki + Jaeger (e2-small)
// HTTP 처리: Gunicorn 2 workers × 2 threads = 4 동시 핸들러
// ★ v2 핵심 특징: OCR이 별도 Worker(speedcam-ocr)에서 비동기 처리
//   - HTTP API는 OCR 부하와 무관하게 동작
//   - OCR 파이프라인 테스트는 mqtt-load-test.py 참조
// Prometheus Remote Write: K6_PROMETHEUS_RW_SERVER_URL=http://10.178.0.5:9090/api/v1/write
//   NOTE: v2 Prometheus는 speedcam-mon(10.178.0.5)에 위치.
//         v1 Prometheus(10.178.0.9)와는 별도 인스턴스입니다.
// Output flag: --out experimental-prometheus-rw
// ============================================================
//
// ★ v1과의 핵심 차이 (비교 분석용):
//   v1: POST /api/v1/crud/cars → 동기 OCR 실행 → HTTP 스레드 3~10초 점유
//       → OCR 부하가 모든 HTTP 요청의 응답시간에 직접 영향
//   v2: OCR이 별도 Worker(speedcam-ocr)에서 비동기 처리
//       → HTTP API는 OCR 부하와 완전히 분리
//       → 이 스크립트의 결과는 "OCR 영향 없는 순수 HTTP 성능"
//   비교 시: v1 동일 시나리오 결과와 비교하면 OCR 분리 효과를 정량화 가능
//
// ============================================================
// 실행 방법
// ============================================================
// 1. Prometheus Remote Write 포함 (Grafana 연동):
//    K6_PROMETHEUS_RW_SERVER_URL=http://10.178.0.5:9090/api/v1/write \
//      k6 run --out experimental-prometheus-rw \
//      --env MAIN_SERVICE_URL=http://localhost \
//      --env TEST_ID=v2-baseline-$(date +%s) \
//      load-test.js
//
// 2. 콘솔 출력만:
//    k6 run \
//      --env MAIN_SERVICE_URL=http://localhost \
//      --env TEST_ID=v2-baseline-$(date +%s) \
//      load-test.js
//
// 실행 위치: speedcam-app 인스턴스 (10.178.0.4 / 34.64.41.106)
// NOTE: MAIN_SERVICE_URL=http://localhost 는 Traefik(port 80)을 통해
//       Django에 접근합니다. 직접 Django 포트(8000)가 아닌 리버스 프록시 경유.
// ============================================================

// ============================================================
// [v2 <-> v1 메트릭 매핑] (비교 분석용)
// ============================================================
// v2: dashboard_req_duration   <->  v1: dashboard_req_duration  (대시보드 응답시간, 공통)
// v2: detections_list_duration <->  v1: cars_list_duration      (목록 조회)
// v2: statistics_req_duration  <->  v1: N/A                     (v2 전용, v1에 대응 없음)
// v2: pending_read_duration    <->  v1: unchecked_req_duration  (미처리 목록)
// v2: admin_req_duration       <->  v1: N/A                     (v2 전용, v1은 동기 OCR POST)
// v2: stress_read_duration     <->  v1: stress_read_duration    (스트레스 읽기, 공통)
// v2: stress_write_duration    <->  v1: stress_write_duration   (스트레스 쓰기, 공통 이름이나 내용 상이)
//     ★ v2 stress_write = 차량 등록 POST (<300ms), v1 stress_write = 동기 OCR POST (3~10초/건)
//     → 이 차이 자체가 핵심 비교 포인트: v1은 20% OCR POST가 전체 시스템을 무너뜨리지만,
//       v2는 OCR과 무관하므로 안정적
// v2: errors                   <->  v1: errors                  (에러율, 공통)
// v2: total_requests           <->  v1: total_requests          (요청 수, 공통)
// ============================================================

// 테스트 실행 ID — Grafana에서 테스트별 필터링 가능
const TEST_ID = __ENV.TEST_ID || `v2-${Date.now()}`;

// -- 커스텀 메트릭 --
const dashboardLatency = new Trend('dashboard_req_duration', true);
const detectionsLatency = new Trend('detections_list_duration', true);
const statisticsLatency = new Trend('statistics_req_duration', true);
const pendingLatency = new Trend('pending_read_duration', true);
const adminLatency = new Trend('admin_req_duration', true);
const errorRate = new Rate('errors');
const requestCount = new Counter('total_requests');
const stressReadLatency  = new Trend('stress_read_duration', true);
const stressWriteLatency = new Trend('stress_write_duration', true);

const BASE_URL = __ENV.MAIN_SERVICE_URL || 'http://main:8000';

// 한국 차량 번호판 생성 (예: 123가4567)
function randomPlate() {
  const nums1 = Math.floor(Math.random() * 900) + 100;
  const chars = '가나다라마바사아자차카타파하';
  const char = chars.charAt(Math.floor(Math.random() * chars.length));
  const nums2 = Math.floor(Math.random() * 9000) + 1000;
  return `${nums1}${char}${nums2}`;
}

// 가짜 FCM 토큰 생성
function randomFCMToken() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let token = '';
  for (let i = 0; i < 152; i++) {
    token += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return token;
}

// ============================================================
// setup: 테스트 데이터 사전 생성 (1회 실행)
// ============================================================
export function setup() {
  // 헬스 체크
  const healthRes = http.get(`${BASE_URL}/health/`);
  const healthOk = check(healthRes, {
    '서버 헬스체크 통과': (r) => r.status === 200,
  });
  if (!healthOk) {
    throw new Error(`서버 연결 실패: ${BASE_URL}`);
  }

  // 테스트 차량 10대 생성 (반복 생성 방지)
  const vehicles = [];
  for (let i = 0; i < 10; i++) {
    const plate = randomPlate();
    const payload = JSON.stringify({
      plate_number: plate,
      owner_name: `테스트차량_${i}`,
      owner_phone: `010-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
    });

    const res = http.post(`${BASE_URL}/api/v1/vehicles/`, payload, {
      headers: { 'Content-Type': 'application/json' },
    });

    if (res.status === 201) {
      const body = res.json();
      vehicles.push({ id: body.id, plate_number: plate });
    }
  }

  console.log(`[Setup] ${vehicles.length}대 테스트 차량 생성 완료`);
  console.log(`[Setup] TEST_ID: ${TEST_ID}`);
  console.log(`[Setup] 인프라: 8x 인스턴스 (OCR 3대 concurrency=5), Gunicorn 2w×2t = 4 핸들러`);
  console.log(`[Setup] ★ v2 비동기 OCR — HTTP API는 OCR 부하와 무관`);
  return { vehicles };
}

// ============================================================
// 시나리오 옵션
// ============================================================
// 용량 기준: Gunicorn 2 workers × 2 threads = 4 동시 핸들러
// 모든 임계치는 load-test-plan.md의 가설에서 도출
// ============================================================
export const options = {
  tags: { test_id: TEST_ID },
  // 타임라인 (총 약 12분 10초):
  //   0m     ~ 2m     : 시나리오 A (대시보드 폴링)
  //   0m     ~ 2m     : 시나리오 B (관리자 작업, A와 동시)
  //   2m     ~ 4m30s  : 시나리오 C (혼합 워크로드)
  //   4m30s  ~ 5m40s  : 시나리오 D (스파이크)
  //   5m40s  ~ 9m10s  : 시나리오 E (스트레스 - 읽기, 50 VUs)
  //   9m10s  ~ 12m10s : 시나리오 F (스트레스 - 혼합, 50 VUs)
  scenarios: {
    // 시나리오 A: 대시보드 폴링 (주요 읽기 부하)
    // 사용자가 대시보드를 열어두고 주기적으로 데이터 확인
    // 예상: p95 < 200ms, 0% 에러 (4 핸들러 용량 범위 내)
    dashboard_polling: {
      executor: 'constant-vus',
      vus: 3,
      duration: '2m',
      startTime: '0s',
      exec: 'dashboardPolling',
      tags: { scenario: 'dashboard_polling' },
    },

    // 시나리오 B: 관리자 작업 (저빈도 쓰기)
    // 관리자가 간헐적으로 차량 등록, FCM 토큰 업데이트
    // 예상: p95 < 300ms, 0% 에러
    admin_ops: {
      executor: 'constant-arrival-rate',
      rate: 2,
      timeUnit: '1m',
      duration: '2m',
      preAllocatedVUs: 2,
      startTime: '0s',
      exec: 'adminOps',
      tags: { scenario: 'admin_ops' },
    },

    // 시나리오 C: 혼합 워크로드 (대시보드 + 관리자 + 파이프라인 읽기)
    // 여러 유형의 요청이 동시 발생하는 현실적 패턴
    // 9 VUs, 4 핸들러 → 피크 시 경합 발생 예상
    // 예상: p95 < 500ms, < 1% 에러
    mixed_workload: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '30s', target: 9 },
        { duration: '1m', target: 9 },
        { duration: '30s', target: 0 },
      ],
      startTime: '2m',
      exec: 'mixedWorkload',
      tags: { scenario: 'mixed_workload' },
    },

    // 시나리오 D: 스파이크 내성 (급격한 트래픽 증가)
    // 15 VUs → 4 핸들러 대비 ~3.75배 초과 구독
    // 예상: p95 < 1500ms, < 10% 에러
    spike_resilience: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 3 },
        { duration: '10s', target: 15 },
        { duration: '30s', target: 15 },
        { duration: '10s', target: 3 },
        { duration: '10s', target: 0 },
      ],
      startTime: '4m30s',
      exec: 'spikeResilience',
      tags: { scenario: 'spike_resilience' },
    },

    // ----------------------------------------------------------
    // 시나리오 E: 스트레스 - 읽기 전용 (한계점 탐색)
    // ----------------------------------------------------------
    // 50 VU → 4 핸들러 = 12.5배 초과 구독
    // v2 핵심: OCR이 분리되어 있으므로 핸들러 전부 읽기에 가용
    // v1 대비: v1은 OCR 잔류 부하로 가용 핸들러가 더 적을 수 있음
    // 가설: p95 < 5000ms, < 20% 에러
    // ----------------------------------------------------------
    stress_ramp: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '30s', target: 30 },
        { duration: '1m',  target: 50 },
        { duration: '30s', target: 30 },
        { duration: '1m',  target: 0  },
      ],
      startTime: '5m40s',
      gracefulStop: '30s',
      exec: 'stressRampV2',
      tags: { scenario: 'stress_ramp' },
    },

    // ----------------------------------------------------------
    // 시나리오 F: 스트레스 - 혼합 (80% 읽기 + 20% 차량 등록)
    // ----------------------------------------------------------
    // ★ v1 비교 핵심: v1은 20% 동기 OCR POST (3~10초/건) → 시스템 붕괴
    //    v2는 20% 차량 등록 POST (<300ms) → OCR과 무관 → 안정
    // 동일 50 VUs, 동일 80/20 비율에서 시스템 안정성 차이 측정
    // 가설: p95 < 30000ms, < 30% 에러
    // ----------------------------------------------------------
    stress_mixed: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '30s', target: 30 },
        { duration: '1m',  target: 50 },
        { duration: '1m',  target: 0  },
      ],
      startTime: '9m10s',
      gracefulStop: '30s',
      exec: 'stressMixedV2',
      tags: { scenario: 'stress_mixed' },
    },
  },

  // 임계치: 4 핸들러 기준으로 보정 (GUNICORN_WORKERS=2)
  thresholds: {
    'dashboard_req_duration': ['p(95)<200'],     // 대시보드 읽기: 200ms 이내
    'detections_list_duration': ['p(95)<300'],    // 감지 목록: 300ms 이내
    'statistics_req_duration': ['p(95)<500'],     // 통계 집계: 500ms 이내
    'pending_read_duration': ['p(95)<500'],       // 대기 목록: 500ms 이내 (비페이지네이션)
    'admin_req_duration': ['p(95)<300'],          // 관리자 쓰기: 300ms 이내
    'http_req_duration{scenario:spike_resilience}': ['p(95)<1500'], // 스파이크: 1500ms 이내
    'errors': ['rate<0.05'],                      // 전체 에러율: 5% 미만
    'errors{scenario:dashboard_polling}': ['rate<0.01'],  // 대시보드: 1% 미만
    'errors{scenario:spike_resilience}': ['rate<0.10'],   // 스파이크: 10% 미만
    // 스트레스 읽기: 50 VUs → 큐잉 심각, 5초 허용
    'stress_read_duration': ['p(95)<5000'],
    // 스트레스 혼합 쓰기(차량등록): 50 VUs에서도 빠른 응답 예상 (OCR 없음)
    'stress_write_duration': ['p(95)<30000'],
    // 스트레스 에러율
    'errors{scenario:stress_ramp}': ['rate<0.20'],
    'errors{scenario:stress_mixed}': ['rate<0.30'],
  },
};

// ============================================================
// 시나리오 A: 대시보드 폴링
// ============================================================
// 실제 패턴: 감지 목록 5초, 알림 10초, 통계 30초 주기 폴링
// iteration 카운트로 요청 유형 분산
// ============================================================
export function dashboardPolling() {
  const iter = exec.scenario.iterationInTest;

  group('대시보드 폴링', () => {
    // 매 iteration: 감지 목록 조회 (5초 주기)
    const detectionsRes = http.get(`${BASE_URL}/api/v1/detections/`);
    check(detectionsRes, {
      '감지 목록 200': (r) => r.status === 200,
    });
    errorRate.add(detectionsRes.status !== 200);
    detectionsLatency.add(detectionsRes.timings.duration);
    dashboardLatency.add(detectionsRes.timings.duration);
    requestCount.add(1);

    // 2회마다: 알림 목록 조회 (10초 주기)
    if (iter % 2 === 0) {
      const notifRes = http.get(`${BASE_URL}/api/v1/notifications/`);
      check(notifRes, {
        '알림 목록 200': (r) => r.status === 200,
      });
      errorRate.add(notifRes.status !== 200);
      dashboardLatency.add(notifRes.timings.duration);
      requestCount.add(1);
    }

    // 6회마다: 통계 조회 (30초 주기)
    if (iter % 6 === 0) {
      const statsRes = http.get(`${BASE_URL}/api/v1/detections/statistics/`);
      check(statsRes, {
        '통계 조회 200': (r) => r.status === 200,
      });
      errorRate.add(statsRes.status !== 200);
      statisticsLatency.add(statsRes.timings.duration);
      dashboardLatency.add(statsRes.timings.duration);
      requestCount.add(1);
    }
  });

  sleep(5); // 5초 폴링 주기
}

// ============================================================
// 시나리오 B: 관리자 작업
// ============================================================
// 저빈도: 차량 등록 + FCM 토큰 업데이트
// constant-arrival-rate로 분당 2회 발생
// ============================================================
export function adminOps(data) {
  group('관리자 작업', () => {
    // 차량 등록
    const plate = randomPlate();
    const createPayload = JSON.stringify({
      plate_number: plate,
      owner_name: `부하테스트_${Date.now()}`,
      owner_phone: `010-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
    });

    const createRes = http.post(`${BASE_URL}/api/v1/vehicles/`, createPayload, {
      headers: { 'Content-Type': 'application/json' },
    });
    check(createRes, {
      '차량 등록 201': (r) => r.status === 201,
    });
    errorRate.add(createRes.status !== 201);
    adminLatency.add(createRes.timings.duration);
    requestCount.add(1);

    // FCM 토큰 업데이트 (setup에서 생성한 차량 사용)
    if (data.vehicles && data.vehicles.length > 0) {
      const vehicle = data.vehicles[Math.floor(Math.random() * data.vehicles.length)];
      const tokenPayload = JSON.stringify({
        fcm_token: randomFCMToken(),
      });

      const tokenRes = http.patch(
        `${BASE_URL}/api/v1/vehicles/${vehicle.id}/fcm-token/`,
        tokenPayload,
        { headers: { 'Content-Type': 'application/json' } }
      );
      check(tokenRes, {
        'FCM 토큰 업데이트 200': (r) => r.status === 200,
      });
      errorRate.add(tokenRes.status !== 200);
      adminLatency.add(tokenRes.timings.duration);
      requestCount.add(1);
    }
  });
}

// ============================================================
// 시나리오 C: 혼합 워크로드
// ============================================================
// 60% 읽기 (감지, 알림, 통계)
// 30% 파이프라인 상태 확인 (/pending/)
// 10% 관리자 쓰기
// 9 VUs → 4 핸들러, 피크 시 경합 발생 예상
// ============================================================
export function mixedWorkload(data) {
  const rand = Math.random();

  if (rand < 0.6) {
    // 60%: 대시보드 읽기
    group('혼합 - 읽기', () => {
      const endpoints = [
        '/api/v1/detections/',
        '/api/v1/notifications/',
        '/api/v1/detections/statistics/',
      ];
      const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
      const res = http.get(`${BASE_URL}${endpoint}`);
      check(res, {
        '혼합 읽기 200': (r) => r.status === 200,
      });
      errorRate.add(res.status !== 200);
      dashboardLatency.add(res.timings.duration);

      if (endpoint.includes('statistics')) {
        statisticsLatency.add(res.timings.duration);
      } else if (endpoint.includes('detections')) {
        detectionsLatency.add(res.timings.duration);
      }
      requestCount.add(1);
    });
  } else if (rand < 0.9) {
    // 30%: 파이프라인 상태 확인 (pending 감지 목록)
    group('혼합 - 파이프라인 상태', () => {
      const res = http.get(`${BASE_URL}/api/v1/detections/pending/`);
      check(res, {
        '대기 목록 200': (r) => r.status === 200,
      });
      errorRate.add(res.status !== 200);
      pendingLatency.add(res.timings.duration);
      requestCount.add(1);
    });
  } else {
    // 10%: 관리자 쓰기
    group('혼합 - 쓰기', () => {
      const plate = randomPlate();
      const payload = JSON.stringify({
        plate_number: plate,
        owner_name: `혼합테스트_${Date.now()}`,
        owner_phone: `010-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
      });

      const res = http.post(`${BASE_URL}/api/v1/vehicles/`, payload, {
        headers: { 'Content-Type': 'application/json' },
      });
      check(res, {
        '혼합 차량 등록': (r) => r.status === 201,
      });
      errorRate.add(res.status !== 201);
      adminLatency.add(res.timings.duration);
      requestCount.add(1);
    });
  }

  sleep(Math.random() * 3 + 2); // 2-5초 랜덤 간격
}

// ============================================================
// 시나리오 D: 스파이크 내성
// ============================================================
// 15 VUs → 4 핸들러 = ~3.75배 초과 구독
// 심각한 요청 큐잉 예상, 핸들러 포화 + MySQL 연결 폭주
// ============================================================
export function spikeResilience() {
  group('스파이크 내성', () => {
    // 대시보드 읽기 엔드포인트를 빠르게 반복 요청
    const detectionsRes = http.get(`${BASE_URL}/api/v1/detections/`);
    check(detectionsRes, {
      '스파이크 감지 목록 200': (r) => r.status === 200,
    });
    errorRate.add(detectionsRes.status !== 200);
    detectionsLatency.add(detectionsRes.timings.duration);
    requestCount.add(1);

    const notifRes = http.get(`${BASE_URL}/api/v1/notifications/`);
    check(notifRes, {
      '스파이크 알림 목록 200': (r) => r.status === 200,
    });
    errorRate.add(notifRes.status !== 200);
    requestCount.add(1);

    const statsRes = http.get(`${BASE_URL}/api/v1/detections/statistics/`);
    check(statsRes, {
      '스파이크 통계 200': (r) => r.status === 200,
    });
    errorRate.add(statsRes.status !== 200);
    statisticsLatency.add(statsRes.timings.duration);
    requestCount.add(1);
  });

  sleep(1); // 스파이크 시 빠른 요청 (1초 간격)
}

// ============================================================
// 시나리오 E: 스트레스 - 읽기 전용 (한계점 탐색)
// ============================================================
// 50 VU → v2 엔드포인트 (detections, notifications, statistics)
// v1과 동일 VU 프로파일 → 핸들러 포화 시점 비교
// v2는 OCR 분리로 순수 읽기 성능만 측정
// ============================================================
export function stressRampV2() {
  group('스트레스 - 읽기', () => {
    const endpoints = [
      '/api/v1/detections/',
      '/api/v1/notifications/',
      '/api/v1/detections/statistics/',
    ];
    const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
    const res = http.get(`${BASE_URL}${endpoint}`, {
      tags: { endpoint: 'stress_read' },
    });
    check(res, {
      '스트레스 읽기 200': (r) => r.status === 200,
    });
    errorRate.add(res.status !== 200);
    stressReadLatency.add(res.timings.duration);
    requestCount.add(1);
  });

  sleep(1); // 빠른 요청 (1초 간격)
}

// ============================================================
// 시나리오 F: 스트레스 - 혼합 (80% 읽기 + 20% 차량 등록)
// ============================================================
// ★ 핵심 비교 시나리오:
//   v1: 20% 동기 OCR POST (3~10초/건) → 핸들러 점유 → 시스템 붕괴
//   v2: 20% 차량 등록 POST (<300ms) → 핸들러 즉시 반환 → 안정
// 동일 50 VUs, 동일 80/20 비율에서 시스템 안정성 차이를 측정
// ============================================================
export function stressMixedV2() {
  if (Math.random() < 0.8) {
    // 80%: 읽기 - v2 엔드포인트
    group('스트레스 혼합 - 읽기', () => {
      const endpoints = [
        '/api/v1/detections/',
        '/api/v1/notifications/',
        '/api/v1/detections/statistics/',
      ];
      const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
      const res = http.get(`${BASE_URL}${endpoint}`, {
        tags: { endpoint: 'stress_mixed_read' },
      });
      check(res, {
        '스트레스 혼합 읽기 200': (r) => r.status === 200,
      });
      errorRate.add(res.status !== 200);
      stressReadLatency.add(res.timings.duration);
      requestCount.add(1);
    });

    sleep(1);
  } else {
    // 20%: 차량 등록 쓰기 (v2에는 동기 OCR 없음 → POST /vehicles)
    // ★ 비교 주의: v1 쓰기 사이클 = sleep(3) + OCR(3~10초) = 6~13초/건
    //              v2 쓰기 사이클 = sleep(3) + POST(<300ms) = ~3.3초/건
    //   → 동일 50 VUs에서 v2가 v1보다 약 2~4배 더 많은 쓰기 요청 발생
    //   → v2 응답시간이 짧은 것은 "OCR 분리" 효과이지 "요청 수가 적어서"가 아님
    group('스트레스 혼합 - 차량 등록', () => {
      const plate = randomPlate();
      const payload = JSON.stringify({
        plate_number: plate,
        owner_name: `스트레스테스트_${Date.now()}`,
        owner_phone: `010-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
      });

      const res = http.post(`${BASE_URL}/api/v1/vehicles/`, payload, {
        headers: { 'Content-Type': 'application/json' },
        tags: { endpoint: 'stress_mixed_write' },
      });
      const ok = res.status === 201;
      check(res, {
        '스트레스 혼합 차량 등록 성공': () => ok,
      });
      errorRate.add(!ok);
      stressWriteLatency.add(res.timings.duration);
      requestCount.add(1);
    });

    sleep(3);
  }
}

// ============================================================
// teardown: 테스트 데이터 정리 (선택적)
// ============================================================
export function teardown(data) {
  if (data.vehicles) {
    let deleted = 0;
    for (const vehicle of data.vehicles) {
      const res = http.del(`${BASE_URL}/api/v1/vehicles/${vehicle.id}/`);
      if (res.status === 204) deleted++;
    }
    console.log(`[Teardown] ${deleted}/${data.vehicles.length}대 테스트 차량 삭제 완료`);
  }
  console.log(`[Teardown] v2 부하테스트 완료 (TEST_ID: ${TEST_ID})`);
  console.log('[Teardown] 주요 측정 포인트:');
  console.log('  - dashboard_req_duration: 대시보드 읽기 응답 시간 (목표: p95 < 200ms)');
  console.log('  - detections_list_duration: 감지 목록 응답 시간 (목표: p95 < 300ms)');
  console.log('  - stress_read_duration: 스트레스 읽기 응답 시간 (목표: p95 < 5000ms)');
  console.log('  - stress_write_duration: 스트레스 쓰기(차량등록) 응답 시간 (목표: p95 < 30000ms)');
  console.log('  - errors{scenario:stress_ramp}: 스트레스 읽기 에러율 (목표: < 20%)');
  console.log('  - errors{scenario:stress_mixed}: 스트레스 혼합 에러율 (목표: < 30%)');
  console.log(`[Teardown] Grafana: http://10.178.0.5:3000 → k6 dashboard 확인`);
}
