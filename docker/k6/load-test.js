import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import exec from 'k6/execution';

// ============================================================
// SpeedCam 부하테스트 - 실제 사용 패턴 기반
// ============================================================
// 인프라: 6x GCP e2-small (2 vCPU, 2 GB RAM)
// HTTP 처리: Gunicorn 2 workers × 2 threads = 4 동시 핸들러
// 가설 기반 임계치 (load-test-plan.md 참조)
// ============================================================

// -- 커스텀 메트릭 --
const dashboardLatency = new Trend('dashboard_req_duration', true);
const detectionsLatency = new Trend('detections_list_duration', true);
const statisticsLatency = new Trend('statistics_req_duration', true);
const pendingLatency = new Trend('pending_read_duration', true);
const adminLatency = new Trend('admin_req_duration', true);
const errorRate = new Rate('errors');
const requestCount = new Counter('total_requests');

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
  return { vehicles };
}

// ============================================================
// 시나리오 옵션
// ============================================================
// 용량 기준: Gunicorn 2 workers × 2 threads = 4 동시 핸들러
// 모든 임계치는 load-test-plan.md의 가설에서 도출
// ============================================================
export const options = {
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
}
