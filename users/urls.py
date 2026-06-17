from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    RegisterView, ProfileView,
    MyCalculationsView, MyShipmentsView,
    TrustedShopListView, TrustedShopDetailView,
)

TokenObtainPairView = extend_schema(
    tags=['auth'], summary='Получить JWT-токены (login)'
)(TokenObtainPairView)

TokenRefreshView = extend_schema(
    tags=['auth'], summary='Обновить access-токен'
)(TokenRefreshView)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', TokenObtainPairView.as_view(), name='token-obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    # Личный кабинет
    path('me/calculations/', MyCalculationsView.as_view(), name='me-calculations'),
    path('me/shipments/', MyShipmentsView.as_view(), name='me-shipments'),
    path('me/trusted-shops/', TrustedShopListView.as_view(), name='me-trusted-shops'),
    path('me/trusted-shops/<int:pk>/', TrustedShopDetailView.as_view(), name='me-trusted-shop-detail'),
]
