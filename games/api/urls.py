from django.urls import include, path
from rest_framework.routers import DefaultRouter

from games.api.views import GameViewSet, PuzzleViewSet

router = DefaultRouter()

router.register(r"", GameViewSet, basename="games")
router.register(r"puzzles", PuzzleViewSet, basename="puzzles")

urlpatterns = [
    path("", include(router.urls))
]
