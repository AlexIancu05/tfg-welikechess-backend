from django.urls import re_path
from chat.websockets import consumers

# noinspection PyTypeChecker
websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_id>\d+)/$', consumers.PrivateChatConsumer.as_asgi()),
]