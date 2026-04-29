from rest_framework import permissions, viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from users.api.permissions import IsOwnerOrReadOnly
from users.api.serializers import *
from users.models import FriendRequest
from users.services import FriendService


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
        elif self.action in ["update", "partial_update", "me"]:
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

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def send_friend_request(self, request, *args, **kwargs):
        """
        Endpoint: api/users/<username>/send_friend_request/
        Envía una solicitud de amistad al usuario especificado
        """
        user_to_befriend = self.get_object()
        sender = request.user

        _success, message, status_code = FriendService.send_friend_request(sender=sender, receiver=user_to_befriend)

        return Response({"detail": message}, status=status_code)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def respond_friend_request(self, request, *args, **kwargs):
        """
        Endpoint: POST api/users/<username>/respond_request/
        Body: {"action": "accept" | "reject"}
        """
        sender = self.get_object()
        user_to_befriend = request.user
        action_type = request.data.get("action")

        _success, message, status_code = FriendService.respond_request(
            sender=sender,
            receiver=user_to_befriend,
            action_type=action_type
        )

        return Response({"detail": message}, status=status_code)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def pending_friend_requests(self, request):
        """
        Endpoint: GET api/users/pending_requests/
        Lista las solicitudes de amistad pendientes del usuario autenticado.
        """
        requests = FriendRequest.objects.filter(receiver=request.user, is_active=True)

        serializer = PendingFriendRequestSerializer(requests, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def remove_friend(self, request, *args, **kwargs):
        """
        Endpoint: POST api/users/<username>/remove_friend/
        Elimina al usuario especificado de tu lista de amigos.
        """

        friend_to_remove = self.get_object()
        user = request.user

        _success, message, status_code = FriendService.remove_friend(user1=user, user2=friend_to_remove)

        return Response({"detail": message}, status=status_code)