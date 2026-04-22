import random
from datetime import timedelta

import chess
from django.utils import timezone

from games.models import Game
from games.websockets.constants import WSErrorCodes


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
    def _search_available_game(user, game_mode, initial_time, increment) -> Game:
        """Busca partidas disponibles para emparejar al usuario que esta buscando partida"""
        user_elo = getattr(user, f"elo_{game_mode}", 1200)
        low_elo = user_elo - 100
        high_elo = user_elo + 100

        filters = {
            f"white_player__elo_{game_mode}__gte": low_elo,
            f"white_player__elo_{game_mode}__lte": high_elo,
        }

        return Game.objects.filter(
            status="waiting",
            mode=game_mode,
            initial_time=initial_time,
            increment=increment,
            **filters
        ).order_by("created_at").first()

    @staticmethod
    def _create_new_game(user, game_mode, initial_time, increment) -> Game:
        """Crea una nueva partida"""

        return Game.objects.create(
            white_player=user,
            status="waiting",
            mode=game_mode,
            initial_time=initial_time,
            increment=increment
        )

    @staticmethod
    def join_queue(user, game_mode="blitz", initial_time=600, increment=0):
        """
        Se une a la cola. En caso de no haber partida, la crea y devuelve estado waiting,
        en caso de si haber devuelve el estado match_found
        """
        MatchmakingService._clean_ghost_games()

        found_game = MatchmakingService._search_available_game(user, game_mode, initial_time, increment)
        if found_game:
            if found_game.white_player == user:
                return None, "error_cloned"

            available_game = MatchmakingService._assign_colors(found_game, user)
            available_game.status = "in_progress"
            available_game.save()
            return available_game, "match_found"

        return MatchmakingService._create_new_game(user, game_mode, initial_time, increment), "waiting"

class GameService:
    @staticmethod
    def process_move(game: Game, user, move_uci: str):
        """

        """
        if game.status != "in_progress":
            return False, "La partida no esta en curso", WSErrorCodes.GENERIC_ERROR

        board = chess.Board(game.current_fen)
        is_white_turn = board.turn == chess.WHITE

        if is_white_turn and user != game.white_player:
            return False, "Turno de blancas", WSErrorCodes.WRONG_TURN
        elif not is_white_turn and user != game.black_player:
            return False, "Turno de negras", WSErrorCodes.WRONG_TURN

        try:
            move = chess.Move.from_uci(move_uci)
        except (ValueError, TypeError):
            return False, "Formato UCI inválido", WSErrorCodes.INVALID_JSON

        if move not in board.legal_moves:
            return False, "Movimiento ilegal", WSErrorCodes.ILLEGAL_MOVE

        san_move = board.san(move)
        game.pgn += f"{san_move} "
        board.push(move)

        game.current_fen = board.fen()
        outcome = board.outcome(claim_draw=True)

        if outcome:
            game.status = "completed"

            if outcome.winner == chess.WHITE:
                game.result = "1-0"
                game.winner = game.white_player
            elif outcome.winner == chess.BLACK:
                game.result = "0-1"
                game.winner = game.black_player
            else:
                game.result = "1/2-1/2"

                termination_map = {
                    chess.Termination.CHECKMATE: "checkmate",
                    chess.Termination.STALEMATE: "draw",  # Rey ahogado
                    chess.Termination.INSUFFICIENT_MATERIAL: "draw",
                    chess.Termination.FIFTY_MOVES: "draw",
                    chess.Termination.THREEFOLD_REPETITION: "draw"
                }
                game.termination_reason = termination_map.get(outcome.termination, "draw")

            game.save()

            return True, {
                "move": move_uci,
                "san": san_move,
                "fen": game.current_fen,
                "status": game.status,
                "result": game.result
            }, None