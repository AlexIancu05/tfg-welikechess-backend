import json
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import chess
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase, APIRequestFactory

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username="player1", elo=1200, **kwargs):
    """Crea un usuario con Elos por defecto."""
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        email=f"{username}@test.com",
        **kwargs,
    )
    user.elo_blitz = elo
    user.elo_rapid = elo
    user.elo_bullet = elo
    user.save()
    return user


def make_game(white, black, status="in_progress", mode="blitz", initial_time=300, increment=0):
    from games.models import Game

    return Game.objects.create(
        white_player=white,
        black_player=black,
        status=status,
        mode=mode,
        initial_time=initial_time,
        increment=increment,
        white_time_left=float(initial_time),
        black_time_left=float(initial_time),
        last_move_at=timezone.now(),
    )


# ===========================================================================
# SERIALIZER TESTS
# ===========================================================================

class PlayerSimpleSerializerTest(TestCase):
    def setUp(self):
        self.user = make_user("alice", elo=1400)

    def test_fields_present(self):
        from games.api.serializers import PlayerSimpleSerializer

        data = PlayerSimpleSerializer(self.user).data
        for field in ("id", "username", "elo_blitz", "elo_rapid", "elo_bullet"):
            self.assertIn(field, data)

    def test_elo_values(self):
        from games.api.serializers import PlayerSimpleSerializer

        data = PlayerSimpleSerializer(self.user).data
        self.assertEqual(data["elo_blitz"], 1400)


class GameListSerializerTest(TestCase):
    def setUp(self):
        self.white = make_user("white_player")
        self.black = make_user("black_player")
        self.game = make_game(self.white, self.black)

    def test_basic_fields(self):
        from games.api.serializers import GameListSerializer

        data = GameListSerializer(self.game).data
        for field in ("id", "mode", "status", "result", "created_at", "white_username", "black_username"):
            self.assertIn(field, data)

    def test_usernames(self):
        from games.api.serializers import GameListSerializer

        data = GameListSerializer(self.game).data
        self.assertEqual(data["white_username"], "white_player")
        self.assertEqual(data["black_username"], "black_player")

    def test_winner_null_when_in_progress(self):
        from games.api.serializers import GameListSerializer

        data = GameListSerializer(self.game).data
        self.assertIsNone(data["winner_username"])

    def test_winner_username_when_completed(self):
        from games.api.serializers import GameListSerializer
        from games.models import Game

        self.game.status = "completed"
        self.game.result = "1-0"
        self.game.winner = self.white
        self.game.termination_reason = "checkmate"
        self.game.save()

        data = GameListSerializer(self.game).data
        self.assertEqual(data["winner_username"], "white_player")


class GameDetailSerializerTest(TestCase):
    def setUp(self):
        self.white = make_user("w")
        self.black = make_user("b")
        self.game = make_game(self.white, self.black)

    def test_nested_players(self):
        from games.api.serializers import GameDetailSerializer

        data = GameDetailSerializer(self.game).data
        self.assertIn("username", data["white_player"])
        self.assertIn("username", data["black_player"])

    def test_duration_none_when_not_finished(self):
        from games.api.serializers import GameDetailSerializer

        data = GameDetailSerializer(self.game).data
        self.assertIsNone(data["duration"])

    def test_duration_calculated(self):
        from games.api.serializers import GameDetailSerializer

        now = timezone.now()
        self.game.finished_at = now
        self.game.created_at  # ya existe
        # Forzar diferencia de 60 segundos
        self.game.finished_at = self.game.created_at + timedelta(seconds=60)
        self.game.save()

        data = GameDetailSerializer(self.game).data
        self.assertAlmostEqual(data["duration"], 60.0, delta=1.0)


class PuzzleSerializerTest(TestCase):
    def setUp(self):
        from games.models import Puzzle

        self.puzzle = Puzzle.objects.create(
            lichess_id="abc123",
            fen=chess.STARTING_FEN,
            moves="e2e4 e7e5 d1h5",
            rating=1300,
            themes="opening,fork",
        )

    def test_fields(self):
        from games.api.serializers import PuzzleSerializer

        data = PuzzleSerializer(self.puzzle).data
        for field in ("lichess_id", "rating", "themes", "fen"):
            self.assertIn(field, data)


class PuzzleAttemptSerializerTest(TestCase):
    def setUp(self):
        from games.models import Puzzle, PuzzleAttempt

        self.user = make_user("solver")
        self.puzzle = Puzzle.objects.create(
            lichess_id="xyz999",
            fen=chess.STARTING_FEN,
            moves="e2e4 e7e5",
            rating=1200,
        )
        self.attempt = PuzzleAttempt.objects.create(
            user=self.user,
            puzzle=self.puzzle,
            successful=True,
        )

    def test_nested_puzzle(self):
        from games.api.serializers import PuzzleAttemptSerializer

        data = PuzzleAttemptSerializer(self.attempt).data
        self.assertIn("puzzle", data)
        self.assertEqual(data["puzzle"]["lichess_id"], "xyz999")

    def test_successful_flag(self):
        from games.api.serializers import PuzzleAttemptSerializer

        data = PuzzleAttemptSerializer(self.attempt).data
        self.assertTrue(data["successful"])


# ===========================================================================
# EloService TESTS
# ===========================================================================

class EloServiceTest(TestCase):
    def test_white_wins_gains_elo(self):
        from games.services import EloService

        new_w, new_b = EloService._calculate_new_elos(1200, 1200, "1-0")
        self.assertGreater(new_w, 1200)
        self.assertLess(new_b, 1200)

    def test_black_wins_gains_elo(self):
        from games.services import EloService

        new_w, new_b = EloService._calculate_new_elos(1200, 1200, "0-1")
        self.assertLess(new_w, 1200)
        self.assertGreater(new_b, 1200)

    def test_draw_close_elos_minimal_change(self):
        from games.services import EloService

        new_w, new_b = EloService._calculate_new_elos(1200, 1200, "1/2-1/2")
        self.assertEqual(new_w, 1200)
        self.assertEqual(new_b, 1200)

    def test_higher_rated_loses_more_when_upset(self):
        from games.services import EloService

        # El jugador débil gana al fuerte
        new_strong, new_weak = EloService._calculate_new_elos(1600, 1200, "0-1")
        loss = 1600 - new_strong
        gain = new_weak - 1200
        self.assertGreater(loss, 10)   # el fuerte pierde bastante
        self.assertGreater(gain, 20)   # el débil gana bastante

    def test_update_player_elos_updates_db(self):
        from games.services import EloService

        white = make_user("ew", elo=1200)
        black = make_user("eb", elo=1200)
        game = make_game(white, black)
        game.status = "completed"
        game.result = "1-0"
        game.termination_reason = "checkmate"
        game.save()

        EloService.update_player_elos(game)

        white.refresh_from_db()
        black.refresh_from_db()
        self.assertGreater(white.elo_blitz, 1200)
        self.assertLess(black.elo_blitz, 1200)

    def test_update_skips_if_not_completed(self):
        from games.services import EloService

        white = make_user("ew2", elo=1200)
        black = make_user("eb2", elo=1200)
        game = make_game(white, black, status="in_progress")

        EloService.update_player_elos(game)  # no debe lanzar ni modificar

        white.refresh_from_db()
        self.assertEqual(white.elo_blitz, 1200)


# ===========================================================================
# MatchmakingService TESTS
# ===========================================================================

class MatchmakingServiceTest(TransactionTestCase):
    def setUp(self):
        self.p1 = make_user("mm1", elo=1200)
        self.p2 = make_user("mm2", elo=1200)

    def test_first_player_creates_waiting_game(self):
        from games.services import MatchmakingService

        game, state = MatchmakingService.join_queue(self.p1, "blitz", 300, 0)
        self.assertEqual(state, "waiting")
        self.assertEqual(game.status, "waiting")

    def test_second_player_finds_match(self):
        from games.services import MatchmakingService

        MatchmakingService.join_queue(self.p1, "blitz", 300, 0)
        game, state = MatchmakingService.join_queue(self.p2, "blitz", 300, 0)
        self.assertEqual(state, "match_found")
        self.assertEqual(game.status, "in_progress")

    def test_same_player_double_join_returns_existing(self):
        from games.services import MatchmakingService

        game1, _ = MatchmakingService.join_queue(self.p1, "blitz", 300, 0)
        game2, state2 = MatchmakingService.join_queue(self.p1, "blitz", 300, 0)
        self.assertEqual(state2, "waiting")
        self.assertEqual(game1.id, game2.id)

    def test_different_modes_dont_match(self):
        from games.services import MatchmakingService

        MatchmakingService.join_queue(self.p1, "blitz", 300, 0)
        game, state = MatchmakingService.join_queue(self.p2, "rapid", 600, 0)
        self.assertEqual(state, "waiting")


# ===========================================================================
# GameService TESTS
# ===========================================================================

class GameServiceMoveTest(TransactionTestCase):
    def setUp(self):
        self.white = make_user("gw", elo=1200)
        self.black = make_user("gb", elo=1200)
        self.game = make_game(self.white, self.black)

    def test_valid_move_accepted(self):
        from games.services import GameService

        success, data, err = GameService.process_move(self.game.id, self.white, "e2e4")
        self.assertTrue(success)
        self.assertIsNone(err)
        self.assertEqual(data["move"], "e2e4")

    def test_illegal_move_rejected(self):
        from games.services import GameService

        success, msg, err = GameService.process_move(self.game.id, self.white, "e2e5")
        self.assertFalse(success)

    def test_wrong_turn_rejected(self):
        from games.services import GameService
        from core.constants import WSErrorCodes

        success, msg, err = GameService.process_move(self.game.id, self.black, "e7e5")
        self.assertFalse(success)
        self.assertEqual(err, WSErrorCodes.WRONG_TURN)

    def test_invalid_uci_format(self):
        from games.services import GameService
        from core.constants import WSErrorCodes

        success, msg, err = GameService.process_move(self.game.id, self.white, "INVALID")
        self.assertFalse(success)
        self.assertEqual(err, WSErrorCodes.INVALID_JSON)

    def test_move_updates_fen(self):
        from games.services import GameService

        GameService.process_move(self.game.id, self.white, "e2e4")
        self.game.refresh_from_db()
        self.assertNotEqual(self.game.current_fen, chess.STARTING_FEN)

    def test_move_updates_pgn(self):
        from games.services import GameService

        GameService.process_move(self.game.id, self.white, "e2e4")
        self.game.refresh_from_db()
        self.assertIn("e4", self.game.pgn)

    def test_increment_applied(self):
        from games.services import GameService

        self.game.increment = 5
        self.game.save()
        _, data, _ = GameService.process_move(self.game.id, self.white, "e2e4")
        # El tiempo de blancas debe ser >= initial_time - elapsed + 5
        self.assertGreaterEqual(data["time_white"], self.game.initial_time)

    def test_move_on_completed_game_fails(self):
        from games.services import GameService

        self.game.status = "completed"
        self.game.result = "1-0"
        self.game.termination_reason = "checkmate"
        self.game.save()

        success, msg, _ = GameService.process_move(self.game.id, self.white, "e2e4")
        self.assertFalse(success)


class GameServiceResignTest(TransactionTestCase):
    def setUp(self):
        self.white = make_user("rw", elo=1200)
        self.black = make_user("rb", elo=1200)
        self.game = make_game(self.white, self.black)

    def test_white_resigns(self):
        from games.services import GameService

        success, data, _ = GameService.resign_game(self.game.id, self.white)
        self.assertTrue(success)
        self.assertEqual(data["result"], "0-1")

    def test_black_resigns(self):
        from games.services import GameService

        success, data, _ = GameService.resign_game(self.game.id, self.black)
        self.assertTrue(success)
        self.assertEqual(data["result"], "1-0")

    def test_non_player_cannot_resign(self):
        from games.services import GameService

        outsider = make_user("outsider")
        success, _, _ = GameService.resign_game(self.game.id, outsider)
        self.assertFalse(success)

    def test_resign_completed_game_fails(self):
        from games.services import GameService

        self.game.status = "completed"
        self.game.result = "1-0"
        self.game.termination_reason = "checkmate"
        self.game.save()

        success, _, _ = GameService.resign_game(self.game.id, self.white)
        self.assertFalse(success)


class GameServiceDrawTest(TransactionTestCase):
    def setUp(self):
        self.white = make_user("dw", elo=1200)
        self.black = make_user("db", elo=1200)
        self.game = make_game(self.white, self.black)

    def test_accept_draw(self):
        from games.services import GameService

        success, data, _ = GameService.accept_draw(self.game.id, self.white)
        self.assertTrue(success)
        self.assertEqual(data["result"], "1/2-1/2")

    def test_draw_sets_no_winner(self):
        from games.services import GameService

        GameService.accept_draw(self.game.id, self.black)
        self.game.refresh_from_db()
        self.assertIsNone(self.game.winner)

    def test_outsider_cannot_accept_draw(self):
        from games.services import GameService

        outsider = make_user("out2")
        success, _, _ = GameService.accept_draw(self.game.id, outsider)
        self.assertFalse(success)


class GameServiceEndGameTest(TransactionTestCase):
    def setUp(self):
        self.white = make_user("ew3", elo=1200)
        self.black = make_user("eb3", elo=1200)
        self.game = make_game(self.white, self.black)

    def test_end_game_idempotent(self):
        from games.services import GameService

        GameService.end_game(self.game, "1-0", self.white, "checkmate")
        GameService.end_game(self.game, "0-1", self.black, "resignation")  # segunda llamada ignorada

        self.game.refresh_from_db()
        self.assertEqual(self.game.result, "1-0")

    def test_end_game_updates_elos(self):
        from games.services import GameService

        GameService.end_game(self.game, "1-0", self.white, "checkmate")
        self.game.refresh_from_db()
        self.assertNotEqual(self.game.white_elo_change, 0)


class GameServiceRecentGamesTest(TestCase):
    def setUp(self):
        self.user = make_user("hist")
        other = make_user("other")
        for _ in range(3):
            g = make_game(self.user, other)
            g.status = "completed"
            g.result = "1-0"
            g.winner = self.user
            g.termination_reason = "checkmate"
            g.save()

    def test_returns_completed_games(self):
        from games.services import GameService

        games = GameService.find_user_recent_games(self.user)
        self.assertEqual(len(games), 3)

    def test_limit_respected(self):
        from games.services import GameService

        games = GameService.find_user_recent_games(self.user, limit=2)
        self.assertEqual(len(games), 2)


class GameServiceClaimVictoryTest(TransactionTestCase):
    def setUp(self):
        self.white = make_user("cv_w", elo=1200)
        self.black = make_user("cv_b", elo=1200)
        self.game = make_game(self.white, self.black)

    def test_claim_timeout_no_time_left(self):
        from games.services import GameService

        # Simular turno de negras con tiempo agotado
        board = chess.Board(self.game.current_fen)
        # Hacer un movimiento para que sea turno de negras
        GameService.process_move(self.game.id, self.white, "e2e4")
        self.game.refresh_from_db()

        # Simular que las negras no tienen tiempo
        self.game.black_time_left = 0
        self.game.last_move_at = timezone.now() - timedelta(seconds=10)
        self.game.save()

        success, data, _ = GameService.claim_victory(self.game.id, self.white, "timeout")
        self.assertTrue(success)
        self.assertEqual(data["result"], "1-0")

    def test_claim_abandonment_too_soon(self):
        from games.services import GameService

        self.game.black_disconnected_at = timezone.now() - timedelta(seconds=10)
        self.game.save()

        success, msg, _ = GameService.claim_victory(self.game.id, self.white, "abandonment")
        self.assertFalse(success)

    def test_claim_abandonment_after_60s(self):
        from games.services import GameService

        self.game.black_disconnected_at = timezone.now() - timedelta(seconds=61)
        self.game.save()

        success, data, _ = GameService.claim_victory(self.game.id, self.white, "abandonment")
        self.assertTrue(success)
        self.assertEqual(data["result"], "1-0")

    def test_claim_invalid_type(self):
        from games.services import GameService

        success, _, _ = GameService.claim_victory(self.game.id, self.white, "unknown_type")
        self.assertFalse(success)

    def test_claim_on_finished_game(self):
        from games.services import GameService

        self.game.status = "completed"
        self.game.result = "1-0"
        self.game.termination_reason = "checkmate"
        self.game.save()

        success, _, _ = GameService.claim_victory(self.game.id, self.white, "timeout")
        self.assertFalse(success)


# ===========================================================================
# JWT MIDDLEWARE TESTS
# ===========================================================================

class JWTAuthMiddlewareTest(TransactionTestCase):
    """
    Usa TransactionTestCase (no envuelve en transacción) y cierra la conexión
    DB tras cada test async para evitar que async_to_sync/database_sync_to_async
    deje la conexión del hilo principal en estado inválido.
    """

    def setUp(self):
        self.user = make_user("jwt_user")

    def tearDown(self):
        # Forzar cierre de la conexión DB tras cada test que usa async_to_sync,
        # para que Django abra una conexión limpia en el siguiente setUp.
        from django.db import connection
        connection.close()

    def _get_token(self):
        from rest_framework_simplejwt.tokens import AccessToken
        return str(AccessToken.for_user(self.user))

    def test_valid_token_resolves_user(self):
        from asgiref.sync import async_to_sync
        from games.websockets.middleware import get_user_from_token

        token = self._get_token()
        resolved = async_to_sync(get_user_from_token)(token)
        self.assertEqual(resolved.id, self.user.id)

    def test_invalid_token_returns_anonymous(self):
        from asgiref.sync import async_to_sync
        from games.websockets.middleware import get_user_from_token

        resolved = async_to_sync(get_user_from_token)("bad_token")
        self.assertIsInstance(resolved, AnonymousUser)

    def test_middleware_injects_user_from_query_string(self):
        from asgiref.sync import async_to_sync
        from games.websockets.middleware import JWTAuthMiddleware

        token = self._get_token()
        scope = {
            "type": "websocket",
            "query_string": f"token={token}".encode(),
        }
        received_scope = {}

        async def fake_app(s, receive, send):
            received_scope.update(s)

        async_to_sync(JWTAuthMiddleware(fake_app))(scope, None, None)
        self.assertEqual(received_scope["user"].id, self.user.id)

    def test_middleware_anonymous_when_no_token(self):
        from asgiref.sync import async_to_sync
        from games.websockets.middleware import JWTAuthMiddleware

        scope = {"type": "websocket", "query_string": b""}
        received_scope = {}

        async def fake_app(s, receive, send):
            received_scope.update(s)

        async_to_sync(JWTAuthMiddleware(fake_app))(scope, None, None)
        self.assertIsInstance(received_scope["user"], AnonymousUser)


# ===========================================================================
# GameViewSet API TESTS
# ===========================================================================

class GameViewSetTest(APITestCase):
    def setUp(self):
        self.user = make_user("api_user")
        self.other = make_user("api_other")
        self.client.force_authenticate(user=self.user)

        self.game = make_game(self.user, self.other)
        self.game.status = "completed"
        self.game.result = "1-0"
        self.game.winner = self.user
        self.game.termination_reason = "checkmate"
        self.game.save()

    def test_my_games_returns_own_games(self):
        response = self.client.get("/api/games/my-games/")
        self.assertEqual(response.status_code, 200)
        ids = [g["id"] for g in response.data]
        self.assertIn(str(self.game.id), ids)

    def test_active_games(self):
        active = make_game(self.user, self.other)  # status="in_progress"
        response = self.client.get("/api/games/active/")
        self.assertEqual(response.status_code, 200)
        ids = [g["id"] for g in response.data]
        self.assertIn(str(active.id), ids)

    def test_player_stats(self):
        response = self.client.get(f"/api/games/player/{self.user.username}/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("total_games", response.data)
        self.assertGreater(response.data["total_games"], 0)

    def test_find_by_player(self):
        response = self.client.get(f"/api/games/player/{self.user.username}/")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/games/my-games/")
        self.assertEqual(response.status_code, 401)


# ===========================================================================
# PuzzleViewSet API TESTS
# ===========================================================================

class PuzzleViewSetTest(APITestCase):
    def setUp(self):
        from games.models import Puzzle

        self.user = make_user("puzzle_user", elo=1200)
        Puzzle.objects.create(
            lichess_id="p001",
            fen=chess.STARTING_FEN,
            moves="e2e4 e7e5",
            rating=1200,
            themes="fork",
        )
        Puzzle.objects.create(
            lichess_id="p002",
            fen=chess.STARTING_FEN,
            moves="d2d4 d7d5",
            rating=1250,
            themes="pin",
        )

    def test_random_puzzle_anonymous(self):
        response = self.client.get("/api/games/puzzles/random/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("id", response.data)

    def test_random_puzzle_with_elo_param(self):
        response = self.client.get("/api/games/puzzles/random/?elo=1200")
        self.assertEqual(response.status_code, 200)

    def test_random_puzzle_out_of_range_returns_404(self):
        response = self.client.get("/api/games/puzzles/random/?elo=9999")
        self.assertEqual(response.status_code, 404)

    def test_solve_puzzle_authenticated(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/games/puzzles/solve/",
            {"lichess_id": "p001", "successful": True},
            format="json",
        )
        self.assertIn(response.status_code, (200, 201))

    def test_solve_puzzle_duplicate_returns_200(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/games/puzzles/solve/",
            {"lichess_id": "p001", "successful": True},
            format="json",
        )
        response = self.client.post(
            "/api/games/puzzles/solve/",
            {"lichess_id": "p001", "successful": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_puzzle_history_requires_auth(self):
        response = self.client.get("/api/games/puzzles/history/")
        self.assertEqual(response.status_code, 401)

    def test_puzzle_history_returns_attempts(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/games/puzzles/solve/",
            {"lichess_id": "p001", "successful": True},
            format="json",
        )
        response = self.client.get("/api/games/puzzles/history/")
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# ChallengeViewSet API TESTS
# ===========================================================================

class ChallengeViewSetTest(APITestCase):
    def setUp(self):
        self.sender = make_user("ch_sender")
        self.receiver = make_user("ch_receiver")
        self.client.force_authenticate(user=self.sender)

    @patch("games.api.views.async_to_sync")
    def test_create_challenge(self, mock_async):
        mock_async.return_value = MagicMock(return_value=None)
        response = self.client.post(
            "/api/games/challenges/create/",
            {
                "receiver_username": self.receiver.username,
                "mode": "blitz",
                "initial_time": 300,
                "increment": 0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("challenge_id", response.data)

    @patch("games.api.views.async_to_sync")
    def test_cannot_challenge_self(self, mock_async):
        mock_async.return_value = MagicMock(return_value=None)
        response = self.client.post(
            "/api/games/challenges/create/",
            {"receiver_username": self.sender.username, "mode": "blitz", "initial_time": 300},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("games.api.views.async_to_sync")
    def test_accept_challenge(self, mock_async):
        from games.models import GameChallenge

        mock_async.return_value = MagicMock(return_value=None)
        challenge = GameChallenge.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            mode="blitz",
            initial_time=300,
            increment=0,
        )
        self.client.force_authenticate(user=self.receiver)
        response = self.client.post(f"/api/games/challenges/{challenge.id}/accept/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("game_id", response.data)

    def test_reject_challenge(self):
        from games.models import GameChallenge

        challenge = GameChallenge.objects.create(
            sender=self.sender,
            receiver=self.receiver,
            mode="blitz",
            initial_time=300,
            increment=0,
        )
        self.client.force_authenticate(user=self.receiver)
        response = self.client.post(f"/api/games/challenges/{challenge.id}/reject/")
        self.assertEqual(response.status_code, 200)
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, "declined")


# ===========================================================================
# MODEL CONSTRAINT TESTS
# ===========================================================================

class GameModelConstraintTest(TestCase):
    def test_termination_reason_only_on_completed(self):
        """termination_reason solo puede estar relleno si status = 'completed'"""
        from django.db import IntegrityError

        white = make_user("mc_w")
        black = make_user("mc_b")

        with self.assertRaises(Exception):
            from games.models import Game

            Game.objects.create(
                white_player=white,
                black_player=black,
                status="in_progress",
                termination_reason="checkmate",  # viola la constraint
            )

    def test_players_must_be_different(self):
        """El mismo jugador no puede ser blancas y negras"""
        player = make_user("solo")
        from django.db import IntegrityError
        from games.models import Game

        with self.assertRaises(Exception):
            Game.objects.create(
                white_player=player,
                black_player=player,
                status="in_progress",
            )


class PuzzleModelTest(TestCase):
    def setUp(self):
        from games.models import Puzzle

        self.puzzle = Puzzle.objects.create(
            lichess_id="pm01",
            fen=chess.STARTING_FEN,
            moves="e2e4 e7e5 d1h5",
            rating=1400,
        )

    def test_get_parsed_moves_structure(self):
        parsed = self.puzzle.get_parsed_moves()
        self.assertIn("blunder_move", parsed)
        self.assertIn("solution", parsed)
        self.assertEqual(parsed["blunder_move"], "e2e4")
        self.assertIsInstance(parsed["solution"], list)
        self.assertEqual(len(parsed["solution"]), 2)

    def test_str_representation(self):
        self.assertIn("pm01", str(self.puzzle))
        self.assertIn("1400", str(self.puzzle))