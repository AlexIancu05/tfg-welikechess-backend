from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response

from chat.api.serializers import PrivateChatRoomSerializer, PrivateMessageSerializer
from chat.services import ChatService
from users.services import UserService

class ChatRoomViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PrivateChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return ChatService.find_user_chats(user)

    @action(detail=False, methods=["post"], url_path="start/(?P<username>[^/.]+)")
    def start_chat(self, request, username=None):
        """
        POST /api/chat/start/<username>/
        """
        user = request.user
        friend = UserService.find_by_username(username)

        room, message, status_code = ChatService.join_room(user=user, friend=friend)
        if status_code != status.HTTP_200_OK:
            return Response({"detail": message}, status=status_code)

        serializer = self.get_serializer(room)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def history(self, request, *args, **kwargs):
        """
        GET /api/chat/<id>/history/
        """
        room = self.get_object()
        if request.user not in [room.user1, room.user2]:
            return Response({"detail": "Acceso denegado"}, status=status.HTTP_403_FORBIDDEN)

        messages = room.messages.order_by("-created_at")[:50]
        serializer = PrivateMessageSerializer(reversed(messages), many=True)
        return Response(serializer.data)