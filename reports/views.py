from rest_framework import generics, permissions
from .serializers import ReportCreateSerializer


class ReportCreateView(generics.CreateAPIView):
    serializer_class = ReportCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
