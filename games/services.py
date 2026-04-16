import random
from datetime import timedelta

from django.utils import timezone

from games.models import Game


class MatchmakingService:

    DEFAULT_MAX_GAME_LIFETIME = 5

    @staticmethod
    def _clean_ghost_games(max_lifetime=DEFAULT_MAX_GAME_LIFETIME):
        """Borra las partidas más antiguas del limite especificado"""
        time_limit = timezone.now() - timedelta(minutes=max_lifetime)
        Game.objects.filter(status="waiting", created_at__lt=time_limit).delete()

    @staticmethod
    def _assign_colors(game, new_player) -> Game:
        """Asigna los colores de los jugadores de manera aleatoria, para evitar ventajas por ping"""
        creator = game.white_player
        if random.choice([True, False]):
            game.white_player = creator
            game.black_player = new_player
        else:
            game.white_player = new_player
            game.black_player = creator

        return game

    @staticmethod
    def _search_available_game(user, game_mode) -> Game:
        """Busca partidas disponibles para emparejar al usuario que esta buscando partida"""
        user_elo = getattr(user, f"elo_{game_mode}", 1200)
        low_elo = user_elo - 100
        high_elo = user_elo + 100

        filters = {
            f"white_player__elo_{game_mode}__gte": low_elo,
            f"white_player__elo_{game_mode}__lte": high_elo
        }

        return Game.objects.filter(
            status="waiting",
            mode=game_mode,
            **filters
        ).order_by("created_at").first()

    @staticmethod
    def _create_new_game(user, game_mode):
        """Crea una nueva partida"""

        return Game.objects.create(
            white_player=user,
            status="waiting",
            mode=game_mode
        )

    @staticmethod
    def join_queue(user, game_mode="blitz"):
        """Se une a la cola. En caso de no haber partida, la crea y devuelve estado waiting,
           en caso de si haber, la encuentra y devuelve el estado match_found"""
        MatchmakingService._clean_ghost_games()

        found_game = MatchmakingService._search_available_game(user, game_mode)
        if found_game:
            if found_game.white_player == user:
                return None, "error_cloned"

            available_game = MatchmakingService._assign_colors(found_game, user)
            available_game.status = "in_progress"
            available_game.save()
            return available_game, "match_found"

        return MatchmakingService._create_new_game(user, game_mode), "waiting"