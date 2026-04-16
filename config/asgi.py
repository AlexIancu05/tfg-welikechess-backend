import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import games.websockets.routing
from games.websockets.middleware import JWTAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

DJANGO_ASGI_APP = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": DJANGO_ASGI_APP,
        "websocket": JWTAuthMiddleware(
            URLRouter(
                games.websockets.routing.websocket_urlpatterns
            )
        )
    }
)
