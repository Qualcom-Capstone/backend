from django.shortcuts import render
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .serializers import PostCreateSerializer
from .models import Post

def index(request):
    return HttpResponse("설정이 완료되었습니다.")
# Create your views here.


@swagger_auto_schema(
    method='post',
    request_body=PostCreateSerializer,
    responses={
        201: openapi.Response(description='게시글 생성 성공', schema=PostCreateSerializer),
        400: '잘못된 요청'
    },
    operation_description="게시글을 생성합니다."
)
@api_view(['POST'])
def create_post(request):
    serializer = PostCreateSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
