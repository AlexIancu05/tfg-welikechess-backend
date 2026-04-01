from rest_framework import permissions, viewsets
from users.api.permissions import IsOwnerOrReadOnly

from users.api.serializers import *
from users.api import services


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializerComplete
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """
        Cambia de serializador dependiendo del usuario
        """

        if self.action == "create":
            return UserRegistrationSerializer
        elif self.action in ["update", "partial_update", "retrieve"]:
            return UserDetailSerializer
        return UserPublicSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]

        elif self.action in ['update', 'partial_update', 'destroy']:
            return [(IsOwnerOrReadOnly | permissions.IsAdminUser)()]

        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()

        if self.action == "list":
            return qs.filter(is_active=True)

        return qs

    def perform_create(self, serializer):
        data = serializer.validated_data

        services.create_user(
            email=data.get("email"),
            username=data.get("username"),
            password=data.get("password")
        )