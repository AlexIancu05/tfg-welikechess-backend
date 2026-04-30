from rest_framework import serializers

from chat.models import PrivateChatRoom, PrivateMessage


class PrivateMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source="sender.username", read_only=True)

    class Meta:
        model = PrivateMessage
        fields = ["id", "sender_username", "text", "is_read", "created_at"]


class PrivateChatRoomSerializer(serializers.ModelSerializer):
    other_user = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = PrivateChatRoom
        fields = ["id", "other_user", "last_message", "last_message_at"]

    def get_other_user(self, obj):
        request = self.context.get("request")

        target = obj.user2 if obj.user1 == request.user else obj.user1

        if target:
            return {"username": target.username, "avatar": target.avatar}
        return {"username": "Cuenta Eliminada", "avatar": None}

    def get_last_message(self, obj):
        last_message = obj.messages.order_by("-created_at").first()

        if last_message:
            return PrivateMessageSerializer(last_message).data
        return None
