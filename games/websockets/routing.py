from django.urls import re_path

from . import consumers

# noinspection PyTypeChecker
websocket_urlpatterns = [
    re_path(r"^ws/matchmaking/", consumers.MatchmakingConsumer.as_asgi()),
    re_path(r"^ws/games/(?P<game_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$", consumers.GameConsumer.as_asgi()),
]