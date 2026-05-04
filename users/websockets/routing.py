from django.urls import re_path

from users.websockets import consumers

# noinspection PyTypeChecker
websocket_urlpatterns = [
    re_path(r"ws/notifications/$", consumers.NotificacionConsumer.as_asgi()),
]