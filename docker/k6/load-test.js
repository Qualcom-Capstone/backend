import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const vehicleCreateDuration = new Trend('vehicle_create_duration', true);

const BASE_URL = __ENV.MAIN_SERVICE_URL || 'http://main:8000';

export const options = {
    scenarios: {
        // Scenario 1: Smoke test (basic connectivity)
        smoke: {
            executor: 'constant-vus',
            vus: 1,
            duration: '10s',
            startTime: '0s',
            tags: { scenario: 'smoke' },
        },
        // Scenario 2: Average load
        average_load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 10 },   // ramp up
                { duration: '1m', target: 10 },     // steady
                { duration: '10s', target: 0 },     // ramp down
            ],
            startTime: '15s',
            tags: { scenario: 'average_load' },
        },
        // Scenario 3: Spike test
        spike: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '5s', target: 30 },    // spike up
                { duration: '15s', target: 30 },   // hold spike
                { duration: '5s', target: 0 },     // recover
            ],
            startTime: '2m',
            tags: { scenario: 'spike' },
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500'],   // 95% of requests under 500ms
        errors: ['rate<0.1'],                // error rate under 10%
    },
};

// Helper to generate random Korean plate number
function randomPlate() {
    const nums1 = Math.floor(Math.random() * 900) + 100;
    const chars = '가나다라마바사아자차카타파하';
    const char = chars.charAt(Math.floor(Math.random() * chars.length));
    const nums2 = Math.floor(Math.random() * 9000) + 1000;
    return `${nums1}${char}${nums2}`;
}

export default function () {
    group('Health Check', function () {
        const res = http.get(`${BASE_URL}/health/`);
        check(res, {
            'health status 200': (r) => r.status === 200,
            'health is healthy': (r) => r.json('status') === 'healthy',
        });
        errorRate.add(res.status !== 200);
    });

    group('Vehicle CRUD', function () {
        // Create
        const plate = randomPlate();
        const createPayload = JSON.stringify({
            plate_number: plate,
            owner_name: `테스트유저_${__VU}`,
            owner_phone: `010-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
        });

        const createRes = http.post(`${BASE_URL}/api/v1/vehicles/`, createPayload, {
            headers: { 'Content-Type': 'application/json' },
        });

        check(createRes, {
            'vehicle created 201': (r) => r.status === 201,
        });
        errorRate.add(createRes.status !== 201);
        vehicleCreateDuration.add(createRes.timings.duration);

        // List
        const listRes = http.get(`${BASE_URL}/api/v1/vehicles/`);
        check(listRes, {
            'vehicle list 200': (r) => r.status === 200,
        });
        errorRate.add(listRes.status !== 200);
    });

    group('Detections Read', function () {
        const res = http.get(`${BASE_URL}/api/v1/detections/`);
        check(res, {
            'detections list 200': (r) => r.status === 200,
        });
        errorRate.add(res.status !== 200);
    });

    group('Notifications Read', function () {
        const res = http.get(`${BASE_URL}/api/v1/notifications/`);
        check(res, {
            'notifications list 200': (r) => r.status === 200,
        });
        errorRate.add(res.status !== 200);
    });

    sleep(1);
}
