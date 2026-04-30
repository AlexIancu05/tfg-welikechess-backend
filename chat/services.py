from django.db import transaction
from django.db.models import Q
from rest_framework import status

from chat.models import PrivateChatRoom
from users.models import User


class ChatService:
    @staticmethod
    def join_room(user: User, friend: User):
        """
        Une a 2 jugadores a la misma sala para que puedan comunicarse
        """
        if user == friend:
            return None, "No puedes abrir un chat contigo mismo", status.HTTP_400_BAD_REQUEST

        if not user.friends.filter(id=friend.id).exists():
            return None, "Debeis ser amigos para poder chatear", status.HTTP_403_FORBIDDEN

        room = ChatService._search_room(user, friend)

        if not room:
            room = ChatService._create_new_room(user, friend)

        return room, "Sala lista", status.HTTP_200_OK

    @staticmethod
    def _search_room(user, friend):
        return PrivateChatRoom.objects.filter(
            (Q(user1=user) & Q(user2=friend)) |
            (Q(user1=friend) & Q(user2=user))
        ).first()

    @staticmethod
    def _create_new_room(user, friend):
        with transaction.atomic():
            return PrivateChatRoom.objects.create(user1=user, user2=friend)

    @staticmethod
    def find_user_chats(user):
        return PrivateChatRoom.objects.filter(Q(user1=user) | Q(user2=user))
