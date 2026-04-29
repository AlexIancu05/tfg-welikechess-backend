from django.conf import settings
from django.db import models

class PrivateChatRoom(models.Model):
    user1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_room_as_user1"
    )

    user2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_room_as_user2"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user1", "user2"]]
        ordering = ["-last_message_at"]

    def __str__(self):
        # Protegemos el acceso en caso de que SET_NULL haya actuado
        u1 = self.user1.username if self.user1 else "Cuenta Eliminada"
        u2 = self.user2.username if self.user2 else "Cuenta Eliminada"
        return f"Chat: {u1} & {u2}"

class PrivateMessage(models.Model):
    room = models.ForeignKey(
        PrivateChatRoom,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_private_messages"
    )
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        sender_username = self.sender.username if self.sender else "Cuenta Eliminada"
        return f"[{self.room.id}] {sender_username}: [Mensaje Cifrado]"