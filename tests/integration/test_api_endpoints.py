"""
Integration Tests for REST API Endpoints
"""
import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status
from apps.vehicles.models import Vehicle
from apps.detections.models import Detection
from apps.notifications.models import Notification


@pytest.fixture
def api_client():
    """테스트용 API Client"""
    return Client()


@pytest.mark.django_db
class TestVehicleAPI:
    """Vehicle API 통합 테스트"""
    
    def test_list_vehicles(self, api_client, sample_vehicle):
        """차량 목록 조회 테스트"""
        response = api_client.get('/api/v1/vehicles/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['count'] >= 1
    
    def test_create_vehicle(self, api_client, db):
        """차량 등록 테스트"""
        data = {
            'plate_number': '78라9012',
            'owner_name': 'API 테스트 사용자',
            'owner_phone': '010-7890-1234'
        }
        response = api_client.post(
            '/api/v1/vehicles/',
            data=data,
            content_type='application/json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Vehicle.objects.filter(plate_number='78라9012').exists()
    
    def test_create_duplicate_vehicle(self, api_client, sample_vehicle):
        """중복 차량 등록 시 에러 테스트"""
        data = {
            'plate_number': sample_vehicle.plate_number,  # 중복
            'owner_name': '중복 테스트',
            'owner_phone': '010-0000-0000'
        }
        response = api_client.post(
            '/api/v1/vehicles/',
            data=data,
            content_type='application/json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_retrieve_vehicle(self, api_client, sample_vehicle):
        """차량 상세 조회 테스트"""
        response = api_client.get(f'/api/v1/vehicles/{sample_vehicle.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['plate_number'] == sample_vehicle.plate_number
    
    def test_update_vehicle_fcm_token(self, api_client, sample_vehicle):
        """FCM 토큰 업데이트 테스트"""
        data = {
            'fcm_token': 'new-fcm-token-updated'
        }
        response = api_client.patch(
            f'/api/v1/vehicles/{sample_vehicle.id}/',
            data=data,
            content_type='application/json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        sample_vehicle.refresh_from_db()
        assert sample_vehicle.fcm_token == 'new-fcm-token-updated'


@pytest.mark.django_db
class TestDetectionAPI:
    """Detection API 통합 테스트"""
    
    def test_list_detections(self, api_client, sample_detection):
        """Detection 목록 조회 테스트"""
        response = api_client.get('/api/v1/detections/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['count'] >= 1
    
    def test_retrieve_detection(self, api_client, sample_detection):
        """Detection 상세 조회 테스트"""
        response = api_client.get(f'/api/v1/detections/{sample_detection.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['camera_id'] == sample_detection.camera_id
    
    def test_filter_detections_by_status(self, api_client, pending_detection, completed_detection):
        """상태별 Detection 필터링 테스트"""
        # pending 상태만 조회
        response = api_client.get('/api/v1/detections/?status=pending')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for result in data['results']:
            assert result['status'] == 'pending'
    
    def test_filter_detections_by_camera(self, api_client, sample_detection):
        """카메라별 Detection 필터링 테스트"""
        response = api_client.get(f'/api/v1/detections/?camera_id={sample_detection.camera_id}')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for result in data['results']:
            assert result['camera_id'] == sample_detection.camera_id


@pytest.mark.django_db
class TestNotificationAPI:
    """Notification API 통합 테스트"""
    
    @pytest.fixture
    def sample_notification(self, db, completed_detection):
        """테스트용 Notification"""
        return Notification.objects.create(
            detection=completed_detection,
            fcm_token='test-token',
            title='테스트 알림',
            body='테스트 내용',
            status='sent'
        )
    
    def test_list_notifications(self, api_client, sample_notification):
        """Notification 목록 조회 테스트"""
        response = api_client.get('/api/v1/notifications/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['count'] >= 1
    
    def test_retrieve_notification(self, api_client, sample_notification):
        """Notification 상세 조회 테스트"""
        response = api_client.get(f'/api/v1/notifications/{sample_notification.id}/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'sent'
    
    def test_filter_notifications_by_status(self, api_client, sample_notification):
        """상태별 Notification 필터링 테스트"""
        response = api_client.get('/api/v1/notifications/?status=sent')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for result in data['results']:
            assert result['status'] == 'sent'


@pytest.mark.django_db
class TestHealthEndpoints:
    """헬스체크 및 기본 엔드포인트 테스트"""
    
    def test_health_check(self, api_client):
        """헬스체크 엔드포인트 테스트"""
        response = api_client.get('/health/')
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'healthy'
    
    def test_home_endpoint(self, api_client):
        """홈 엔드포인트 테스트"""
        response = api_client.get('/')
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_swagger_docs(self, api_client):
        """Swagger 문서 엔드포인트 테스트"""
        response = api_client.get('/swagger/')
        
        assert response.status_code == status.HTTP_200_OK

