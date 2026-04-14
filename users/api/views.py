from rest_framework import permissions, viewsets, filters
from users.api.permissions import IsOwnerOrReadOnly

from users.api.serializers import *


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()

    lookup_field = "username"
    filter_backends = [filters.SearchFilter]
    search_fields = ["username"]

    serializer_class = UserPublicSerializer

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
        if self.action == "create":
            return [permissions.AllowAny()]

        if self.action in ["retrieve", "list", "metadata"]:
            return [permissions.AllowAny()]

        if self.action in ["update", "partial_update", "destroy"]:
            return [(IsOwnerOrReadOnly | permissions.IsAdminUser)()]

        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()

        if self.action == "list":
            return qs.filter(is_active=True)

        return qs

    def perform_create(self, serializer):
        serializer.save()