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

from . import serializers
from .models import CarData, DeviceToken
from .serializers import CarDataSerializer
from crud.tasks import send_speeding_alert

from .image_download import download_image_from_s3  # GCS 사용 (하위 호환 함수명)
from .ocr import process_pil_image_roi_for_plate_ocr # 수정된 OCR 함수


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
        operation_description="""차량 데이터를 생성합니다.
            s3_key를 이용해 이미지를 다운로드하고, 제공된 x,y,w,h 좌표로 OCR을 수행하여 차량번호를 추출합니다.
            추출된 차량번호와 x,y,w,h 좌표를 함께 저장합니다.""",
        request_body=CarDataSerializer,  #
        responses={
            201: CarDataSerializer(),  #
            400: "Bad Request - 유효성 검사 오류 또는 OCR 실패"
        }
    )
    def post(self, request):  #
        mutable_data = request.data.copy()  # 수정 가능한 데이터 복사본

        s3_key = mutable_data.get("s3_key")
        # POST 요청에서 x, y, w, h 좌표 직접 받기
        roi_x = mutable_data.get("x")
        roi_y = mutable_data.get("y")
        roi_w = mutable_data.get("w")
        roi_h = mutable_data.get("h")

        extracted_car_number = None
        ocr_note = None  # OCR 관련 참고 또는 오류 메시지

        # s3_key와 ROI 좌표가 모두 있어야 OCR 수행
        if s3_key and all(coord is not None for coord in [roi_x, roi_y, roi_w, roi_h]):
            try:
                # 1. GCS에서 이미지 다운로드 (image_download.py 사용)
                pil_image = download_image_from_s3(s3_key)  # 함수명은 호환성 유지

                # 2. OCR 수행 (수정된 ocr.py 함수 호출)
                # s3_key를 파일명 힌트로 전달
                ocr_result = process_pil_image_roi_for_plate_ocr(
                    pil_image,
                    float(roi_x), float(roi_y), float(roi_w), float(roi_h),  # serializer에서 float으로 변환되지만 명시적 변환
                    image_file_name_hint=s3_key
                )

                extracted_car_number = ocr_result.get('car_number')
                ocr_note = ocr_result.get('error')  # 오류 메시지가 있다면 저장

                if extracted_car_number and not ocr_note:
                    mutable_data['car_number'] = extracted_car_number  # 추출된 번호로 업데이트
                    print(f"OCR 성공: 차량번호 '{extracted_car_number}' 추출")
                elif ocr_note:
                    print(f"OCR 처리 중 참고/오류: {ocr_note}. 추출된 번호(기본값 가능): '{extracted_car_number}'")
                    if extracted_car_number:  # 기본값이라도 일단 mutable_data에 반영 (serializer에서 처리)
                        mutable_data['car_number'] = extracted_car_number
                else:  # 번호도 없고 오류도 없는 경우 (예: 기본값 로직이 없거나 빈 문자열 반환)
                    print(f"OCR 결과 차량번호 없음. 반환된 번호: '{extracted_car_number}'")


            except Exception as e:
                ocr_note = f"이미지 다운로드 또는 OCR 처리 중 예외 발생: {str(e)}"
                print(ocr_note)
        elif not s3_key:
            ocr_note = "GCS 키가 제공되지 않아 OCR을 수행하지 않았습니다."
            print(ocr_note)
        else:  # s3_key는 있지만 좌표가 없는 경우
            ocr_note = "OCR을 위한 x,y,w,h 좌표가 모두 제공되지 않았습니다."
            print(ocr_note)

        # x,y,w,h 좌표는 이미 mutable_data에 있으므로 serializer가 처리

        serializer = CarDataSerializer(data=mutable_data)  #
        try:
            serializer.is_valid(raise_exception=True)  #
        except serializers.ValidationError as e:
            error_detail = e.detail.copy()
            if ocr_note:  # OCR 관련 메시지가 있다면 응답에 추가
                if 'car_number' in error_detail and isinstance(error_detail['car_number'],
                                                               list) and not extracted_car_number:
                    # car_number 필드 오류에 OCR 실패 원인 추가 (추출된 번호가 아예 없을 때)
                    error_detail['car_number'].append(f"(OCR 참고: {ocr_note})")
                else:  # 다른 필드 오류거나, car_number 오류가 다른 형식이거나, 이미 번호가 있는 경우
                    error_detail['ocr_note'] = ocr_note  # 별도 필드로 OCR 노트 추가
            return Response(error_detail, status=status.HTTP_400_BAD_REQUEST)

        car = serializer.save()  # # car_number, x, y, w, h 포함하여 저장

        payload = {  #
            "id": car.id,  #
            "timestamp": getattr(car, "detected_at", timezone.now()).isoformat(),  #
            "car_number": car.car_number,  #
            "car_speed": car.car_speed,  #
        }
        transaction.on_commit(lambda: send_speeding_alert.delay(payload))  #
        return Response(CarDataSerializer(car).data, status=status.HTTP_201_CREATED)  #


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
