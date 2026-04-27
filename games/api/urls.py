from django.urls import include, path
from rest_framework.routers import DefaultRouter

from games.api.views import GameViewSet

router = DefaultRouter()

router.register(r"", GameViewSet, basename="games")

urlpatterns = [
    path("", include(router.urls))
]