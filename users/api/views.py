from rest_framework import permissions, viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response

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

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def global_ranking(self, request):
        """
        Endpoint: api/users/global_ranking/?type=bullet
        Lee el tipo de ranking desde la URL y lo solicita al servicio.
        """
        perf_type = request.query_params.get("type", "blitz")
        data = services.get_external_ranking(perf_type)

        return Response(data)

    @action(detail=False, methods=["get", "patch"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        user = request.user
        if request.method == "GET":
            serializer = UserDetailSerializer(user)
            return Response(serializer.data)
        serializer = UserDetailSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)