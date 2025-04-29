from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from .models import CarData
from .serializers import CarDataSerializer


class CustomPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = 'page_size'
    max_page_size = 100

@api_view(['POST'])
def create_car_data(request):
    """
    차량 데이터를 생성합니다.
    """
    serializer = CarDataSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def get_car_data_list(request):
    """
    모든 차량 데이터를 페이지네이션하여 조회합니다.
    """
    cars = CarData.objects.all()
    return get_paginated_response(request, cars)


@api_view(['GET'])
def get_checked_car_data_list(request):
    """
    is_checked가 True인 차량 데이터를 페이지네이션하여 조회합니다.
    """
    cars = CarData.objects.filter(is_checked=True)
    return get_paginated_response(request, cars)


@api_view(['GET'])
def get_unchecked_car_data_list(request):
    """
    is_checked가 False인 차량 데이터를 페이지네이션하여 조회합니다.
    """
    cars = CarData.objects.filter(is_checked=False)
    return get_paginated_response(request, cars)


def get_paginated_response(request, queryset):
    """
    주어진 쿼리셋을 페이지네이션하여 응답을 생성합니다.
    """
    paginator = CustomPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = CarDataSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['PUT'])
def update_car_data(request, pk):
    """
    특정 차량 데이터의 is_checked 필드를 업데이트합니다.
    """
    car = get_object_or_404(CarData, pk=pk)
    serializer = CarDataSerializer(car, data=request.data, partial=True)  # partial=True: 부분 업데이트 허용
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
def delete_car_data(request, pk):
    """
    특정 차량 데이터를 삭제합니다.
    """
    car = get_object_or_404(CarData, pk=pk)
    car.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)