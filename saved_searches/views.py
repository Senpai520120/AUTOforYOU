from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SavedSearch
from .serializers import SavedSearchSerializer


class SavedSearchListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SavedSearch.objects.filter(user=request.user)
        return Response(SavedSearchSerializer(qs, many=True).data)

    def post(self, request):
        sr = SavedSearchSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        obj = sr.save(user=request.user)
        return Response(SavedSearchSerializer(obj).data, status=status.HTTP_201_CREATED)


class SavedSearchDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        obj = get_object_or_404(SavedSearch, pk=pk, user=request.user)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk):
        obj = get_object_or_404(SavedSearch, pk=pk, user=request.user)
        sr = SavedSearchSerializer(obj, data=request.data, partial=True)
        sr.is_valid(raise_exception=True)
        sr.save()
        return Response(SavedSearchSerializer(obj).data)
