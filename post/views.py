from django.shortcuts import render
from django.http import HttpResponse
from drf_yasg import openapi
from drf_yasg.openapi import Response
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import api_view, action

from .models import SpeedViolation
from .serializers import SpeedViolationSerializer

def index(request):
    return HttpResponse("설정이 완료되었습니다.")
# Create your views here.

class SpeedViolationViewSet(viewsets.ModelViewSet):
    #ModelViewSet : 자동으로 CREATE, READ, UPDATE, DELETE 기능을 모두 제공
    queryset = SpeedViolation.objects.all().order_by('-timestamp') #최신순 정렬
    serializer_class = SpeedViolationSerializer

    # API 문서화
    @swagger_auto_schema(
        operation_description="과속 차량 목록 조회",
        responses={200: SpeedViolationSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        #GET /api/v1/violations/
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="과속 차량 상세 조회",
        responses={200: SpeedViolationSerializer} #단일 객체라 many=True가 없음
    )
    def retrieve(self, request, *args, **kwargs):
        #GET /api/v1/violations/{id}/
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=SpeedViolationSerializer,
        operation_description="과속 차량 생성",
        responses={
            201: openapi.Response(description="과속 차량 생성 성공", schema=SpeedViolationSerializer),
            400: "잘못된 요청"
        }
    )
    def create(self, request, *args, **kwargs):
        #POST /api/v1/violations/
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=SpeedViolationSerializer,
        operation_description="과속 차량 수정",
        responses={
            200: openapi.Response(description="과속 차량 수정 성공", schema=SpeedViolationSerializer),
            400: "잘못된 요청"
        }
    )
    def update(self, request, *args, **kwargs):
        #PUT /api/v1/violations/{id}/
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=SpeedViolationSerializer,
        operation_description="과속 차량 부분 수정",
        responses={
            200: openapi.Response(description="부분 수정 성공", schema=SpeedViolationSerializer),
            400: "잘못된 요청"
        }
    )
    def partial_update(self, request, *args, **kwargs):
        #PATCH /api/v1/violations/{id}/
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_description="과속 차량 삭제",
        responses={204: "삭제 성공"}
    )
    def destroy(self, request, *args, **kwargs):
        #DELETE /api/v1/violations/{id}/
        return super().destroy(request, *args, **kwargs)