from django.urls import path, include
from rest_framework.routers import DefaultRouter

from chat.api.views import ChatRoomViewSet

router = DefaultRouter()

router.register(r"", ChatRoomViewSet, basename="chat")

urlpatterns = [
    path("", include(router.urls))
]