from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CustomUser, DealerApplication, TrustedShop
from .serializers import (
    DealerApplicationCreateSerializer, DealerApplicationSerializer,
    RegisterSerializer, UserProfileSerializer, TrustedShopSerializer,
)
from .services import DuplicatePendingError, apply_for_dealer


@extend_schema(tags=['auth'], summary='Регистрация нового пользователя')
class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema_view(
    get=extend_schema(tags=['auth'], summary='Получить профиль текущего пользователя'),
    put=extend_schema(tags=['auth'], summary='Обновить профиль'),
    patch=extend_schema(tags=['auth'], summary='Частично обновить профиль'),
)
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# --- Личный кабинет ---

@extend_schema(tags=['me'], summary='История моих расчётов')
class MyCalculationsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from pricing.models import Calculation
        return Calculation.objects.filter(user=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        from pricing.serializers import CalculationSerializer
        return CalculationSerializer


@extend_schema(tags=['me'], summary='Мои отслеживаемые контейнеры')
class MyShipmentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from shipments.models import Shipment
        return Shipment.objects.filter(watchers=self.request.user).prefetch_related('vehicles')

    def get_serializer_class(self):
        from shipments.serializers import ShipmentListSerializer
        return ShipmentListSerializer


@extend_schema_view(
    get=extend_schema(tags=['me'], summary='Мои проверенные партнёры (СТО, маляры, запчасти)'),
    post=extend_schema(tags=['me'], summary='Добавить партнёра'),
)
class TrustedShopListView(generics.ListCreateAPIView):
    serializer_class = TrustedShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TrustedShop.objects.filter(owner=self.request.user)


@extend_schema_view(
    get=extend_schema(tags=['me'], summary='Детали партнёра'),
    put=extend_schema(tags=['me'], summary='Обновить партнёра'),
    patch=extend_schema(tags=['me'], summary='Частично обновить партнёра'),
    delete=extend_schema(tags=['me'], summary='Удалить партнёра'),
)
class TrustedShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TrustedShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TrustedShop.objects.filter(owner=self.request.user)


# --- Верификация дилеров ---

@extend_schema(
    tags=['dealers'],
    summary='Подать заявку на статус дилера',
    description=(
        'Создаёт заявку со статусом pending. '
        'Повторная подача при наличии pending-заявки возвращает 409.'
    ),
)
class DealerApplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DealerApplicationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            application = apply_for_dealer(
                user=request.user,
                **serializer.validated_data,
            )
        except DuplicatePendingError as e:
            return Response({'detail': str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(DealerApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['dealers'],
    summary='Статус собственной заявки',
    description='Возвращает последнюю заявку текущего пользователя (или 404).',
)
class DealerApplicationStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        application = (
            DealerApplication.objects.filter(user=request.user).order_by('-created_at').first()
        )
        if not application:
            return Response({'detail': 'Заявка не найдена.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(DealerApplicationSerializer(application).data)
