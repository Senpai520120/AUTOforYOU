from django.urls import path

from .views import (
    AuthConfigView,
    CookieTokenObtainView,
    CookieTokenRefreshView,
    CsrfView,
    DealerApplicationStatusView,
    DealerApplyView,
    LogoutView,
    MyCalculationsView,
    MyShipmentsView,
    ProfileView,
    RegisterView,
    ResendVerificationView,
    TrustedShopDetailView,
    TrustedShopListView,
    VerifyEmailView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('verify-email/resend/', ResendVerificationView.as_view(), name='auth-verify-email-resend'),
    path('config/', AuthConfigView.as_view(), name='auth-config'),
    path('csrf/', CsrfView.as_view(), name='auth-csrf'),
    path('token/', CookieTokenObtainView.as_view(), name='token-obtain'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('token/logout/', LogoutView.as_view(), name='token-logout'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    # Личный кабинет
    path('me/calculations/', MyCalculationsView.as_view(), name='me-calculations'),
    path('me/shipments/', MyShipmentsView.as_view(), name='me-shipments'),
    path('me/trusted-shops/', TrustedShopListView.as_view(), name='me-trusted-shops'),
    path('me/trusted-shops/<int:pk>/', TrustedShopDetailView.as_view(), name='me-trusted-shop-detail'),
]

dealer_urlpatterns = [
    path('apply/', DealerApplyView.as_view(), name='dealer-apply'),
    path('application/', DealerApplicationStatusView.as_view(), name='dealer-application'),
]
