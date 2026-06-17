from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions
from .models import CustomUser
from .serializers import RegisterSerializer, UserProfileSerializer


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
