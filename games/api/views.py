from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from games.api.serializers import *
from games.models import Game


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    lookup_field = "id"

    def get_queryset(self):
        return Game.objects.select_related(
            "white_player",
            "black_player",
            "winner"
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GameDetailSerializer
        return GameListSerializer

    @action(detail=False, methods=["get"], url_path="my-history")
    def my_games(self, request):
        """
        Devuelve el historial del usuario que hace la peticion
        Endpoint: GET /api/games/my-history/
        """

        user = request.user

        qs = self.get_queryset().filter(
            Q(white_player=user) | Q(black_player=user)
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="active")
    def active_games(self, request):
        """
        Devuelve todas las partidas que se estan jugando actualmente
        Endpoint: GET /api/games/active/
        """

        qs = self.get_queryset().filter(Q(status="in_progress"))
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path=r"player/(?P<username>[^/.]+)")
    def find_by_player(self, request, username=None):
        """
        Devuelve el historial publico de un jugador
        Endpoint: GET /api/games/player/username_jugador
        """

        qs = self.get_queryset().filter(
            Q(white_player__username__iexact=username) |
            Q(black_player__username__iexact=username)
        )

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
