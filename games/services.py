import random
from datetime import timedelta

import chess
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from twisted.internet.iocpreactor.reactor import MAX_TIMEOUT

from games.models import Game
from core.constants import WSErrorCodes


class MatchmakingService:
    DEFAULT_MAX_GAME_LIFETIME = 5

    @staticmethod
    def _clean_ghost_games(max_lifetime=DEFAULT_MAX_GAME_LIFETIME):
        """Borra las partidas más antiguas del limite especificado"""
        time_limit = timezone.now() - timedelta(minutes=max_lifetime)
        Game.objects.filter(
            status="waiting",
            created_at__lt=time_limit
        ).select_for_update(skip_locked=True).delete()

    @staticmethod
    def _assign_colors(game, new_player) -> Game:
        """Asigna los colores de los jugadores de manera aleatoria, para evitar ventajas por ping"""
        creator = game.white_player
        if random.choice([True, False]):
            game.white_player, game.black_player = creator, new_player
        else:
            game.white_player, game.black_player = new_player, creator
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

        return (Game.objects.select_for_update(skip_locked=True).filter(
            status="waiting",
            mode=game_mode,
            initial_time=initial_time,
            increment=increment,
            **filters
        ).exclude(
            white_player=user
        ).order_by("created_at").first())

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
        with transaction.atomic():
            MatchmakingService._clean_ghost_games()

            # Control para que no se pueda emparejar consiguo mismo si abre mas de una pestaña
            existing_waiting_game = Game.objects.filter(white_player=user, status="waiting").first()
            if existing_waiting_game:
                return existing_waiting_game, "waiting"

            found_game = MatchmakingService._search_available_game(user, game_mode, initial_time, increment)
            if found_game:
                available_game = MatchmakingService._assign_colors(found_game, user)
                available_game.status = "in_progress"
                available_game.white_time_left = float(initial_time)
                available_game.black_time_left = float(initial_time)
                available_game.last_move_at = timezone.now()
                available_game.save()
                return available_game, "match_found"

        return MatchmakingService._create_new_game(user, game_mode, initial_time, increment), "waiting"


class GameService:
    @staticmethod
    def _process_outcome(game, outcome):
        if not outcome:
            return

        if outcome.winner == chess.WHITE:
            match_result, winner = "1-0", game.white_player
        elif outcome.winner == chess.BLACK:
            match_result, winner = "0-1", game.black_player
        else:
            match_result, winner = "1/2-1/2", None

        termination_map = {
            chess.Termination.CHECKMATE: "checkmate",
            chess.Termination.STALEMATE: "draw",  # Rey ahogado
            chess.Termination.INSUFFICIENT_MATERIAL: "draw",
            chess.Termination.FIFTY_MOVES: "draw",
            chess.Termination.THREEFOLD_REPETITION: "draw",
        }
        reason = termination_map.get(outcome.termination, "draw")
        GameService.end_game(game, match_result, winner, reason)

    @staticmethod
    def end_game(game, match_result, winner, reason):
        """
        Acaba una partida
        """

        # Para evitar que se ejecute mas de una vez
        if game.status == "completed":
            return

        with transaction.atomic():
            game.status = "completed"
            game.result = match_result
            game.winner = winner
            game.termination_reason = reason
            EloService.update_player_elos(game)
            game.save()

    @staticmethod
    def process_move(game_id, user, move_uci):
        """
        Valida un movimiento en el tablero
        """
        # Recibe el id y se reinstancia para evitar race conditions
        with transaction.atomic():
            game = Game.objects.select_for_update().get(id=game_id)

            if game.status != "in_progress":
                return False, "La partida no esta en curso", WSErrorCodes.GENERIC_ERROR

            board = chess.Board(game.current_fen)
            is_white_turn = board.turn == chess.WHITE
            now = timezone.now()

            if (is_white_turn and user != game.white_player) or (not is_white_turn and user != game.black_player):
                return False, "No es tu turno", WSErrorCodes.WRONG_TURN

            # Validar formato y legibilidad del movimiento
            try:
                move = chess.Move.from_uci(move_uci)
            except (ValueError, TypeError):
                return False, "Formato UCI inválido", WSErrorCodes.INVALID_JSON

            if move not in board.legal_moves:
                return False, "Movimiento ilegal", WSErrorCodes.ILLEGAL_MOVE

            # Calcular tiempo gastado
            elapsed = (now - game.last_move_at).total_seconds()

            if is_white_turn:
                game.white_time_left = max(0.0, game.white_time_left - elapsed)
                timeout = game.white_time_left <= 0
            else:
                game.black_time_left = max(0.0, game.black_time_left - elapsed)
                timeout = game.black_time_left <= 0

            # Ver si perdio por timeout
            if timeout:
                if is_white_turn:
                    GameService.end_game(game, match_result="0-1", winner=game.black_player, reason="timeout")
                else:
                    GameService.end_game(game, match_result="1-0", winner=game.white_player, reason="timeout")

                return True, {
                    "move": None,
                    "san": None,
                    "fen": game.current_fen,
                    "status": game.status,
                    "result": game.result,
                    "time_white": game.white_time_left,
                    "time_black": game.black_time_left,
                    "white_elo_change": game.white_elo_change,
                    "black_elo_change": game.black_elo_change
                }, None

            # Aplicar incremento
            if is_white_turn:
                game.white_time_left += game.increment
            else:
                game.black_time_left += game.increment

            san_move = board.san(move)

            if is_white_turn:
                move_number = board.fullmove_number
                game.pgn += f"{move_number}. {san_move} "
            else:
                game.pgn += f"{san_move} "

            board.push(move)

            game.current_fen = board.fen()
            game.last_move_at = now

            outcome = board.outcome(claim_draw=True)
            GameService._process_outcome(game, outcome)

            if game.status == "in_progress":
                game.save()

            return True, {
                "move": move_uci,
                "san": san_move,
                "fen": game.current_fen,
                "status": game.status,
                "result": game.result if game.status == "completed" else None,
                "time_white": game.white_time_left,
                "time_black": game.black_time_left,
                "white_elo_change": game.white_elo_change if game.status == "completed" else None,
                "black_elo_change": game.black_elo_change if game.status == "completed" else None
            }, None

    @staticmethod
    def resign_game(game_id, user):
        """
        Pide la rendicion de un jugador
        """
        with transaction.atomic():
            game = Game.objects.select_for_update().get(id=game_id)

            if game.status != "in_progress":
                return False, "La partida no esta en curso", WSErrorCodes.GENERIC_ERROR

            if user == game.white_player:
                winner = game.black_player
                match_result = "0-1"
            elif user == game.black_player:
                winner = game.white_player
                match_result = "1-0"
            else:
                return False, "Jugador no presente en la partida", WSErrorCodes.GENERIC_ERROR

            GameService.end_game(game=game, match_result=match_result, winner=winner, reason="resignation")

            return True, {
                "action": "game_ended",
                "fen": game.current_fen,
                "status": game.status,
                "result": game.result,
                "termination_reason": game.termination_reason
            }, None

    @staticmethod
    def accept_draw(game_id, user):
        """
        Procesa la aceptacion de un empate
        """
        with transaction.atomic():
            game = Game.objects.select_for_update().get(id=game_id)

            if game.status != "in_progress":
                return False, "La partida no esta en curso", WSErrorCodes.GENERIC_ERROR

            if user not in [game.white_player, game.black_player]:
                return False, "Jugador no presente en la partida", WSErrorCodes.GENERIC_ERROR

            GameService.end_game(game=game, match_result="1/2-1/2", winner=None, reason="agreed_draw")

            return True, {
                "action": "game_ended",
                "fen": game.current_fen,
                "status": game.status,
                "result": game.result,
                "termination_reason": game.termination_reason
            }, None

    @staticmethod
    def find_user_recent_games(user, limit=10):
        games = Game.objects.filter(
            (Q(white_player=user) | Q(black_player=user)) & Q(status="completed")
        ).order_by('-created_at')[:limit]

        return [
            {
                "id": str(game.id),
                "mode": game.mode,
                "result": game.result,
                "white": game.white_player.username if game.white_player else "Anónimo",
                "black": game.black_player.username if game.black_player else "Anónimo",
                "date": game.created_at
            }
            for game in games
        ]

    @staticmethod
    def claim_victory(game_id, user, claim_type, max_seconds=60):
        game = Game.objects.get(id=game_id)
        if game.status != "in_progress":
            return False, "La partida ya ha terminado", WSErrorCodes.GENERIC_ERROR

        now = timezone.now()
        is_white = (user == game.white_player)

        if claim_type == "abandonment":
            opponent_disconnect_time = game.black_disconnected_at if is_white else game.white_disconnected_at

            if not opponent_disconnect_time:
                return False, "El rival no está desconectado", WSErrorCodes.GENERIC_ERROR

            time_offline = (now - opponent_disconnect_time).total_seconds()
            if time_offline >= max_seconds:
                result = "1-0" if is_white else "0-1"
                winner = game.white_player if is_white else game.black_player

                GameService.end_game(game=game, match_result=result, winner=winner, reason="disconnected")

                return True, {
                    "action": "game_over",
                    "result": game.result,
                    "reason": "Abandono por desconexión"
                }, 200
            else:
                return False, "Aún no han pasado 60 segundos", WSErrorCodes.GENERIC_ERROR

        elif claim_type == "timeout":
            is_white_turn = game.current_fen.split(" ")[1] == "w"

            if is_white and not is_white_turn:
                time_spent = (now - game.last_move_at).total_seconds()
                real_time_left = game.black_time_left - time_spent
                if real_time_left <= 0:
                    GameService.end_game(game=game, match_result="1-0", winner=game.white_player, reason="timeout")
                    return True, {
                        "action": "game_over",
                        "result": "1-0",
                        "reason": "Tiempo agotado"
                    }, 200

            elif not is_white and is_white_turn:
                time_spent = (now - game.last_move_at).total_seconds()
                real_time_left = game.white_time_left - time_spent
                if real_time_left <= 0:
                    GameService.end_game(game=game, match_result="0-1", winner=game.black_player, reason="timeout")
                    return True, {
                        "action": "game_over",
                        "result": "0-1",
                        "reason": "Tiempo agotado"
                    }, 200

            return False, "El rival aún tiene tiempo", WSErrorCodes.GENERIC_ERROR

        return False, "Tipo de reclamación inválida", WSErrorCodes.GENERIC_ERROR

class EloService:
    K_FACTOR = 32

    @staticmethod
    def _calculate_new_elos(white_elo: int, black_elo: int, match_result: str) -> tuple[int, int]:
        """
        Calcula las nuevas puntuaciones Elo tras una partida.
        result debe ser "1-0" (blancas ganan), "0-1" (negras ganan) o "1/2-1/2" (tablas)
        Devuelve: (nuevo_elo_blancas, nuevo_elo_negras)
        """
        # Formula para probabilidad matematica de victoria
        expected_white = 1 / (1 + 10 ** ((black_elo - white_elo) / 400))
        expected_black = 1 / (1 + 10 ** ((white_elo - black_elo) / 400))

        # Asignar puntuacion segun resultado
        if match_result == "1-0":
            score_white, score_black = 1, 0
        elif match_result == "0-1":
            score_white, score_black = 0, 1
        else:
            score_white, score_black = 0.5, 0.5

        # Formula calculo elo
        new_white_elo = white_elo + EloService.K_FACTOR * (score_white - expected_white)
        new_black_elo = black_elo + EloService.K_FACTOR * (score_black - expected_black)

        return round(new_white_elo), round(new_black_elo)

    @staticmethod
    def update_player_elos(game):
        """
        Lee el resultado de la partida, calcula y actualiza a los jugadores en la BBDD.
        """

        if game.status != "completed" or not game.result:
            return

        User = get_user_model()
        white_player = User.objects.select_for_update().get(id=game.white_player.id)
        black_player = User.objects.select_for_update().get(id=game.black_player.id)
        mode = game.mode

        white_elo = getattr(white_player, f"elo_{mode}", 1200)
        black_elo = getattr(black_player, f"elo_{mode}", 1200)

        new_white_elo, new_black_elo = EloService._calculate_new_elos(white_elo, black_elo, game.result)

        setattr(white_player, f"elo_{mode}", new_white_elo)
        setattr(black_player, f"elo_{mode}", new_black_elo)

        white_player.save()
        black_player.save()
