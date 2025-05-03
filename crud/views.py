# backend/crud/views.py
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from .models import CarData
from .serializers import CarDataSerializer

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi # 필요한 경우 사용

class CustomPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100

@swagger_auto_schema(
    method='get', # GET 메서드 스키마 정의
    responses={200: CarDataSerializer(many=True)} # 목록 조회 응답 스키마 (페이지네이션 구조는 drf-yasg가 자동 처리)
)
@swagger_auto_schema(
    method='post', # POST 메서드 스키마 정의
    request_body=CarDataSerializer, # POST 요청의 Request Body는 CarDataSerializer를 따름
    responses={
        201: CarDataSerializer, # 201 Created 응답 시
        400: "Bad Request - Validation Errors"
    }
)
@api_view(['GET', 'POST']) # GET과 POST 메서드를 모두 허용
def car_list_create_view(request):
    """
    차량 목록을 조회하거나 새로운 차량 데이터를 생성합니다.
    (GET /api/v1/crud/cars/, POST /api/v1/crud/cars/)
    """
    if request.method == 'GET':
        cars = CarData.objects.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(cars, request)
        serializer = CarDataSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    elif request.method == 'POST':
        serializer = CarDataSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# DELETE 요청: 특정 차량 삭제
@swagger_auto_schema(
    method='get', # GET 메서드 스키마 정의
    responses={
        200: CarDataSerializer, # 200 OK 응답 시
        404: "Not Found" # 404 Not Found 응답 시
    }
)
@swagger_auto_schema(
    method='put', # PUT 메서드 스키마 정의
    request_body=CarDataSerializer, # PUT 요청의 Request Body는 CarDataSerializer를 따름
    responses={
        200: CarDataSerializer, # 200 OK 응답 시
        400: "Bad Request - Validation Errors",
        404: "Not Found"
    }
)
@swagger_auto_schema(
    method='patch', # PATCH 메서드 스키마 정의 (부분 업데이트)
    request_body=CarDataSerializer, # PATCH 요청의 Request Body는 CarDataSerializer를 따름
    responses={
        200: CarDataSerializer, # 200 OK 응답 시
        400: "Bad Request - Validation Errors",
        404: "Not Found"
    }
)
@swagger_auto_schema(
    method='delete', # DELETE 메서드 스키마 정의
    responses={
        204: "No Content - Successfully Deleted", # 204 No Content 응답 시
        404: "Not Found"
    }
)
@api_view(['GET', 'PUT', 'PATCH', 'DELETE']) # GET, PUT, PATCH, DELETE 메서드를 모두 허용
def car_detail_view(request, pk):
    """
    특정 ID를 가진 차량 데이터를 조회, 업데이트 또는 삭제합니다.
    (GET, PUT, PATCH, DELETE /api/v1/crud/cars/{id}/)
    """
    car = get_object_or_404(CarData, pk=pk)

    if request.method == 'GET':
        serializer = CarDataSerializer(car)
        return Response(serializer.data)

    elif request.method == 'PUT':
        # PUT은 일반적으로 전체 업데이트를 의미하지만, DRF Serializer는 partial=True로 부분 업데이트도 지원
        serializer = CarDataSerializer(car, data=request.data) # PUT은 partial=False가 기본
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'PATCH':
        # PATCH는 부분 업데이트를 의미
        serializer = CarDataSerializer(car, data=request.data, partial=True) # partial=True 명시
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    elif request.method == 'DELETE':
        car.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# /api/v1/crud/cars/checked/ 경로 (GET 요청)
@api_view(['GET'])
def get_checked_car_data_list(request):
    """
    is_checked가 True인 차량 데이터를 페이지네이션하여 조회합니다. (GET /api/v1/crud/cars/checked/)
    """
    cars = CarData.objects.filter(is_checked=True)
    return get_paginated_response(request, cars)

# /api/v1/crud/cars/unchecked/ 경로 (GET 요청)
@api_view(['GET'])
def get_unchecked_car_data_list(request):
    """
    is_checked가 False인 차량 데이터를 페이지네이션하여 조회합니다. (GET /api/v1/crud/cars/unchecked/)
    """
    cars = CarData.objects.filter(is_checked=False)
    return get_paginated_response(request, cars)

# 페이지네이션 응답 생성 헬퍼 함수 (동일)
def get_paginated_response(request, queryset):
    """
    주어진 쿼리셋을 페이지네이션하여 응답을 생성합니다.
    """
    paginator = CustomPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = CarDataSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)