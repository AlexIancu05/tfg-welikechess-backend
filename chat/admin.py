from django.contrib import admin
from .models import PrivateChatRoom, PrivateMessage


@admin.register(PrivateChatRoom)
class PrivateChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'user1', 'user2', 'last_message_at', 'created_at')
    search_fields = ('user1__username', 'user2__username')
    raw_id_fields = ('user1', 'user2')
    readonly_fields = ('created_at', 'last_message_at')


@admin.register(PrivateMessage)
class PrivateMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('sender__username', 'text', 'room__id')
    raw_id_fields = ('room', 'sender')