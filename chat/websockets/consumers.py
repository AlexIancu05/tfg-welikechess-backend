import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from chat.models import PrivateChatRoom, PrivateMessage
from core.constants import WSErrorCodes
from users.services import UserService


class PrivateChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.room_id = None
        self.room_group_name = None

    async def send_error(self, message: str, close_connection: bool = False, close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
        """
        Envía mensajes de error al front.
        Si close_connection es True, cierra el Websocket
        close_code son codigos de errores nuestros internos, todos estando en constants.WSErrorCodes
        """
        await self.send(text_data=json.dumps(
            {
                "type": "error",
                "code": close_code,
                "message": message
            }
        ))

        if close_connection:
            await self.close()

    async def connect(self):
        self.user = self.scope["user"]
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_{self.room_id}"

        if not self.user.is_authenticated:
            await self.close()
            return

        is_member = await self.is_room_member(self.user.id, self.room_id)
        if not is_member:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, code):
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data = None, bytes_data = None):
        """
        Recibe el mensaje del Frontend
        *Se asume que el mensaje ya esta cifrado
        """
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except Exception:
            await self.send_error(message="Formato JSON inválido", close_code=WSErrorCodes.INVALID_JSON)
            return

        encrypted_text = data.get("text")

        msg = await self.save_message(self.user.username, self.room_id, encrypted_text)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message_id": msg.id,
                "sender_username": self.user.username,
                "text": msg.text,
                "created_at": str(msg.created_at)
            }
        )

    async def chat_message(self, event):
        """
        Envía el mensaje de vuelta al WebSocket del Frontend
        """

        await self.send(text_data=json.dumps(
            {
                "id": event["message_id"],
                "sender_username": event["sender_username"],
                "text": event["text"],
                "created_at": event["created_at"]
            }
        ))

    @database_sync_to_async
    def is_room_member(self, user_id, room_id):
        try:
            room = PrivateChatRoom.objects.get(id=room_id)
            return user_id in [room.user1_id, room.user2_id]
        except PrivateChatRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, username, room_id, text):
        room = PrivateChatRoom.objects.get(id=room_id)
        sender = UserService.find_by_username(username)

        room.last_message_at = timezone.now()
        room.save()

        return PrivateMessage.objects.create(
            room=room,
            sender=sender,
            text=text
        )