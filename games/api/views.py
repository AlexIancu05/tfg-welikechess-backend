import random

from django.db.models import Q, Count
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from games.api.serializers import *
from games.models import Game, Puzzle


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

    @action(detail=False, methods=["get"], url_path="my-games")
    def my_games(self, request):
        """
        Devuelve el historial del usuario que hace la petición
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
        Devuelve todas las partidas que se están jugando actualmente
        Endpoint: GET /api/games/active/
        """

        qs = self.get_queryset().filter(Q(status="in_progress"))
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path=r"player/(?P<username>[^/.]+)")
    def find_by_player(self, request, username=None):
        """
        Devuelve el historial público de un jugador
        Endpoint: GET /api/games/player/username_jugador
        """

        qs = self.get_queryset().filter(
            Q(white_player__username__iexact=username) |
            Q(black_player__username__iexact=username)
        )

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path=r"player/(?P<username>[^/.]+)/stats")
    def player_stats(self, request, username=None):
        """
        Devuelve las estadísticas de un jugador (Total, Victorias, Derrotas, Empates)
        Endpoint: GET /api/games/player/username_jugador/stats/
        """

        qs = self.get_queryset().filter(
            Q(white_player__username__iexact=username) |
            Q(black_player__username__iexact=username),
            status="completed"
        )

        stats = qs.aggregate(
            total_games=Count("id"),
            games_won=Count("id", filter=Q(winner__username__iexact=username)),
            games_draw=Count("id", filter=Q(winner__isnull=True))
        )

        total = stats["total_games"]
        won = stats["games_won"]
        draw = stats["games_draw"]
        lost = total - won - draw

        winrate = round((won / total * 100), 2) if total > 0 else 0
        lossrate = round((lost / total * 100), 2) if total > 0 else 0
        drawrate = round((draw / total * 100), 2) if total > 0 else 0

        return Response({
            "total_games": total,
            "games_won": won,
            "games_lost": lost,
            "games_draw": draw,
            "winrate": winrate,
            "lossrate": lossrate,
            "drawrate": drawrate
        })


class PuzzleViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]

    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    queryset = Puzzle.objects.all()

    @action(detail=False, methods=["get"], url_path="random")
    def random_puzzle(self, request):
        """
        Devuelve un puzle aleatorio adaptado al Elo del usuario
        Endpoint: GET /api/games/puzzles/random/?elo=1400 (el parámetro es opcional)
        """

        if "elo" in request.query_params:
            try:
                target_elo = int(request.query_params.get("elo"))
            except ValueError:
                target_elo = 1200
        elif request.user.is_authenticated:
            target_elo = getattr(request.user, 'elo_blitz', 1200)
        else:
            target_elo = 1200

        min_elo = target_elo - 100
        max_elo = target_elo + 100

        puzzles_qs = self.get_queryset().filter(
            rating__gte=min_elo,
            rating__lte=max_elo
        )

        if request.user.is_authenticated:
            puzzles_qs = puzzles_qs.exclude(puzzleattempt__user=request.user)

        puzzles_qs = puzzles_qs[:50]

        if not puzzles_qs.exists():
            return Response({"error": "No hay puzles en este rango"}, status=404)

        puzzle = random.choice(puzzles_qs)
        parsed_moves = puzzle.get_parsed_moves()

        return Response({
            "id": puzzle.lichess_id,
            "rating": puzzle.rating,
            "themes": puzzle.themes.split(","),
            "initial_fen": puzzle.fen,
            "blunder_move": parsed_moves["blunder_move"],
            "solution": parsed_moves["solution"]
        })

    @action(detail=False, methods=["post"], url_path="solve", permission_classes=[permissions.IsAuthenticated])
    def solve_puzzle(self, request):
        """
        Guarda el intento de un puzle.
        Endpoint: POST /api/games/puzzles/solve/
        Body: {"lichess_id": "00sLi", "successful": true}
        """
        lichess_id = request.data.get("lichess_id")
        successful = request.data.get("successful")

        if lichess_id is None or successful is None:
            return Response({"error": "Faltan datos (lichess_id, successful)"}, status=400)

        puzzle = get_object_or_404(Puzzle, lichess_id=lichess_id)

        attempt, created = PuzzleAttempt.objects.get_or_create(
            user=request.user,
            puzzle=puzzle,
            defaults={'successful': successful}
        )

        if not created:
            return Response({"message": "Este puzle ya estaba en tu historial."}, status=200)

        return Response({"message": "Intento guardado correctamente."}, status=201)

    @action(detail=False, methods=["get"], url_path="history", permission_classes=[permissions.IsAuthenticated])
    def history(self, request):
        """
        Devuelve el historial de puzles jugados por el usuario.
        Endpoint: GET /api/games/puzzles/history/
        """
        attempts = PuzzleAttempt.objects.filter(user=request.user).select_related('puzzle').order_by('-created_at')

        page = self.paginate_queryset(attempts)

        if page is not None:
            serializer = PuzzleAttemptSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PuzzleAttemptSerializer(attempts, many=True)
        return Response(serializer.data)