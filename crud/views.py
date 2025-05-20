# views.py
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status, generics, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import transaction

from .models import CarData, DeviceToken
from .serializers import CarDataSerializer
from crud.tasks import send_speeding_alert

class CustomPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100


class CarListCreateView(APIView):
    @swagger_auto_schema(
        operation_description="차량 목록을 조회합니다.",
        responses={200: CarDataSerializer(many=True)}
    )
    def get(self, request):
        cars = CarData.objects.all()
        paginator = CustomPagination()
        page = paginator.paginate_queryset(cars, request)
        serializer = CarDataSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_description="차량 데이터를 생성합니다.",
        request_body=CarDataSerializer,
        responses={
            201: CarDataSerializer(),
            400: "Bad Request - Validation Errors"
        }
    )
    def post(self, request):
        serializer = CarDataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        car = serializer.save()
        payload = {
            "id": car.id,
            "timestamp": getattr(car, "detected_at", timezone.now()).isoformat(),
            "car_number": car.car_number,
            "car_speed": car.car_speed,
        }
        transaction.on_commit(lambda: send_speeding_alert.delay(payload))
        return Response(CarDataSerializer(car).data, status=201)


class CarRetrieveUpdateDeleteView(APIView):
    @swagger_auto_schema(
        operation_description="차량 데이터를 조회합니다.",
        responses={200: CarDataSerializer(), 404: "Not Found"}
    )
    def get(self, request, pk):
        car = get_object_or_404(CarData, pk=pk)
        return Response(CarDataSerializer(car).data)

    @swagger_auto_schema(
        operation_description="차량 데이터를 전체 수정합니다.",
        request_body=CarDataSerializer,
        responses={200: CarDataSerializer(), 400: "Bad Request", 404: "Not Found"}
    )
    def put(self, request, pk):
        car = get_object_or_404(CarData, pk=pk)
        serializer = CarDataSerializer(car, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="차량 데이터를 삭제합니다.",
        responses={204: "No Content", 404: "Not Found"}
    )
    def delete(self, request, pk):
        car = get_object_or_404(CarData, pk=pk)
        car.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CarPartialUpdateView(APIView):
    @swagger_auto_schema(
        operation_description="차량 데이터를 부분 수정합니다.",
        request_body=CarDataSerializer,
        responses={200: CarDataSerializer(), 400: "Bad Request", 404: "Not Found"}
    )
    def patch(self, request, pk):
        car = get_object_or_404(CarData, pk=pk)
        serializer = CarDataSerializer(car, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CheckedCarDataListView(APIView):
    @swagger_auto_schema(
        operation_description="is_checked=True인 차량 데이터 목록을 조회합니다.",
        responses={200: CarDataSerializer(many=True)}
    )
    def get(self, request):
        cars = CarData.objects.filter(is_checked=True)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(cars, request)
        serializer = CarDataSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UncheckedCarDataListView(APIView):
    @swagger_auto_schema(
        operation_description="is_checked=False인 차량 데이터 목록을 조회합니다.",
        responses={200: CarDataSerializer(many=True)}
    )
    def get(self, request):
        cars = CarData.objects.filter(is_checked=False)
        paginator = CustomPagination()
        page = paginator.paginate_queryset(cars, request)
        serializer = CarDataSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RegisterFCMTokenView(APIView):
    @swagger_auto_schema(
        operation_description="FCM 토큰을 등록합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'token': openapi.Schema(type=openapi.TYPE_STRING, description='FCM device token'),
            },
            required=['token']
        ),
        responses={204: "Token Registered", 400: "Bad Request"}
    )
    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "token 필드가 필요합니다."}, status=400)
        DeviceToken.objects.get_or_create(token=token)
        return Response(status=204)
