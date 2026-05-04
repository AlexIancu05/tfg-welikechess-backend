import json
import os

import chess
import chess.engine
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer, AsyncWebsocketConsumer
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from core.constants import WSErrorCodes
from games.models import Game, GameMessage
from games.services import MatchmakingService, GameService


class MatchmakingConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket_group_name = None

    def send_error(self, message: str, close_connection: bool = False,
                   close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
        """
        Envía mensajes de error al front.
        Si close_connection es True, cierra el Websocket
        close_code son codigos de errores nuestros internos, todos estando en constants.WSErrorCodes
        """
        self.send(text_data=json.dumps(
            {
                "type": "error",
                "code": close_code,
                "message": message
            }
        ))

        if close_connection:
            self.close()

    def connect(self):
        if self.scope["user"].is_authenticated:
            self.accept()
        else:
            self.close()

    def disconnect(self, code):
        if self.ticket_group_name:
            async_to_sync(self.channel_layer.group_discard)(
                self.ticket_group_name,
                self.channel_name
            )

            # Borramos la partida si este WebSocket en concreto estaba esperando
            game_id_str = self.ticket_group_name.replace("ticket_", "")
            Game.objects.filter(id=game_id_str, status="waiting").delete()

    def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return

        try:
            text_data_json = json.loads(text_data)
        except Exception:
            self.send_error(message="Formato JSON inválido", close_code=WSErrorCodes.INVALID_JSON)
            return

        action = text_data_json.get("action")
        game_mode = text_data_json.get("mode", "blitz")
        initial_time = text_data_json.get("initial_time", 600)
        increment = text_data_json.get("increment", 0)

        if action == "search_game":
            game, status = MatchmakingService.join_queue(self.scope["user"], game_mode, initial_time, increment)

            if status == "match_found":
                ticket_group = f"ticket_{game.id}"

                async_to_sync(self.channel_layer.group_send)(
                    ticket_group,
                    {
                        "type": "match_found",
                        "game_id": str(game.id)
                    }
                )

                self.send(text_data=json.dumps(
                    {
                        "type": "match_found",
                        "game_id": str(game.id)
                    }
                ))
            elif status == "waiting":
                self.ticket_group_name = f"ticket_{game.id}"
                async_to_sync(self.channel_layer.group_add)(
                    self.ticket_group_name,
                    self.channel_name
                )
                self.send(text_data=json.dumps(
                    {
                        "type": "waiting",
                        "message": "Buscando rival..."
                    }
                ))
            elif status == "error_cloned":
                self.send_error(message="No puedes jugar contra tí mismo", close_code=WSErrorCodes.REPEATED_PLAYER)
            else:
                self.send_error(message=f"Estado desconocido: '{status}'", close_code=WSErrorCodes.GENERIC_ERROR)
        else:
            self.send_error(message=f"Acción desconocida: '{action}'", close_code=WSErrorCodes.GENERIC_ERROR)

    def match_found(self, event):
        self.send(text_data=json.dumps(
            {
                "type": "match_found",
                "game_id": event["game_id"]
            }
        ))


class GameConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_id = None
        self.room_group_name = None
        self.game = None
        self.user = None

    def send_error(self, message: str, close_connection: bool = False,
                   close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
        """
        Envía mensajes de error al front.
        Si close_connection es True, cierra el Websocket
        close_code son codigos de errores nuestros internos, todos estando en constants.WSErrorCodes
        """
        self.send(text_data=json.dumps(
            {
                "type": "error",
                "code": close_code,
                "message": message
            }
        ))

        if close_connection:
            self.close(code=close_code)

    def _get_player_color(self):
        user = self.scope["user"]
        if self.game.white_player == user:
            return "w"
        elif self.game.black_player == user:
            return "b"
        else:
            return None

    def _serialize_player(self, player):
        if player is None:
            return None
        return {
            "id": str(player.id),
            "username": player.username,
            "elo_blitz": getattr(player, "elo_blitz", 1200),
            "elo_rapid": getattr(player, "elo_rapid", 1200),
            "elo_bullet": getattr(player, "elo_bullet", 1200),
        }

    def connect(self):
        self.user = self.scope["user"]
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        self.room_group_name = f"game{self.game_id}"

        self.accept()

        # Control de seguridad del usuario, si no esta autenticado, se cierra el Websocket
        if not self.user.is_authenticated:
            self.send_error(message="Usuario no autenticado", close_connection=True,
                            close_code=WSErrorCodes.UNAUTHENTICATED)
            return

        # Cargar partida
        try:
            self.game = Game.objects.select_related("white_player", "black_player").get(id=self.game_id)
        except ObjectDoesNotExist:
            self.send_error(message="Partida no encontrada", close_connection=True,
                            close_code=WSErrorCodes.GAME_NOT_FOUND)
            return

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )

        color = self._get_player_color()
        if color == "w":
            self.game.white_disconnected_at = None
        elif color == "b":
            self.game.black_disconnected_at = None
        self.game.save(update_fields=['white_disconnected_at', 'black_disconnected_at'])

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_message",
                "message": {
                    "action": "player_reconnected",
                    "color": color
                }
            }
        )

        self.send(text_data=json.dumps({
            "type": "game_state",
            "fen": self.game.current_fen,
            "status": self.game.status,
            "color": color,
            "initial_time": self.game.initial_time,
            "increment": self.game.increment,
            "time_white": self.game.white_time_left,
            "time_black": self.game.black_time_left,
            "mode": self.game.mode,
            "white_player": self._serialize_player(self.game.white_player),
            "black_player": self._serialize_player(self.game.black_player),
        }))

    def disconnect(self, code):
        if not (self.room_group_name and self.game):
            return

        color = self._get_player_color()
        now = timezone.now()

        if color == "w":
            self.game.white_disconnected_at = now
        elif color == "b":
            self.game.black_disconnected_at = now
        self.game.save(update_fields=['white_disconnected_at', 'black_disconnected_at'])

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_message",
                "message": {
                    "action": "player_disconnected",
                    "color": color,
                    "timestamp": now.isoformat()
                }
            }
        )

        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            self.send_error(message="Formato JSON inválido", close_code=WSErrorCodes.INVALID_JSON)
            return

        action = data.get("action")

        if action == "make_move":
            self.handle_move(data.get("move"))
        elif action == "resign":
            self.handle_resign()
        elif action == "offer_draw":
            self.handle_offer_draw()
        elif action == "accept_draw":
            self.handle_accept_draw()
        elif action == "chat_message":
            self.handle_chat_message(data.get("message"))
        elif action == "claim_victory":
            self.handle_claim_victory(data.get("claim_type"))
        else:
            self.send_error(message=f"Acción desconocida: '{action}'", close_code=WSErrorCodes.GENERIC_ERROR)

    def handle_move(self, move_uci):
        """Procesa un movimiento en formato UCI. EJ: e2e4"""
        self.game.refresh_from_db()

        success, result_data, error_code = GameService.process_move(self.game_id, self.user, move_uci)

        if not success:
            self.send_error(message=result_data, close_code=error_code)
            return

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_update",
                **result_data
            }
        )

    def game_update(self, event):
        self.send(text_data=json.dumps({
            "type": "game_update",
            "move": event["move"],
            "san": event["san"],
            "fen": event["fen"],
            "status": event["status"],
            "result": event["result"],
            "time_white": event.get("time_white"),
            "time_black": event.get("time_black"),
            "white_elo_change": event.get("white_elo_change"),
            "black_elo_change": event.get("black_elo_change"),
        }))

    def handle_resign(self):
        success, data, error_code = GameService.resign_game(self.game_id, self.user)
        if success:
            self.broadcast_game_update(data)
        else:
            self.send_error(message=data, close_code=error_code)

    def handle_offer_draw(self):
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_message",
                "message": {
                    "action": "draw_offered",
                    "sender": self.user.username
                }
            }
        )

    def handle_accept_draw(self):
        success, data, error_code = GameService.accept_draw(self.game_id, self.user)
        if success:
            self.broadcast_game_update(data)
        else:
            self.send_error(message=data, close_code=error_code)

    def broadcast_game_update(self, data):
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_message",
                "message": data
            }
        )

    def game_message(self, event):
        self.send(text_data=json.dumps(event["message"]))

    def handle_chat_message(self, message_text):
        """Procesa un mensaje de chat, lo guarda y lo difunde"""
        if not message_text or not isinstance(message_text, str):
            return

        clean_text = message_text.strip()

        if not clean_text:
            return

        message = GameMessage.objects.create(
            game=self.game,
            sender=self.user,
            text=clean_text
        )

        if message:
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "username": self.user.username,
                    "message": clean_text
                }
            )

    def chat_message(self, event):
        """Envia el mensaje recibido al grupo del Websocket"""
        self.send(text_data=json.dumps(
            {
                "type": "chat_message",
                "username": event["username"],
                "message": event["message"]
            }
        ))

    def handle_claim_victory(self, claim_type):
        """
        Puede ser "timeout" o "abandonment" (60 segundos desconectado)
        """
        self.game.refresh_from_db()

        success, result_data, error_code = GameService.claim_victory(self.game_id, self.user, claim_type)

        if not success:
            self.send_error(message=result_data, close_code=error_code)
            return

        self.broadcast_game_update(result_data)


class AIGameConsumer(AsyncWebsocketConsumer):
    async def send_error(self, message: str, close_connection: bool = False,
                         close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
        """
        Envía mensajes de error al front.
        Si close_connection es True, cierra el Websocket
        close_code son codigos de errores nuestros internos, todos estando en constants.WSErrorCodes
        """
        await self.send(text_data=json.dumps(
            {
                "type": "error",
                "code": close_code,
                "message": message
            }
        ))

        if close_connection:
            await self.close(code=close_code)

    def __init__(self, *args, **kwargs):
        self.board = None
        self.engine_path = None
        self.transport = None
        self.engine = None

        super().__init__(*args, **kwargs)

    async def connect(self):
        await self.accept()

        self.board = chess.Board()
        self.engine_path = settings.STOCKFISH_PATH

        self.transport, self.engine = await chess.engine.popen_uci(self.engine_path)

        skill_level = int(self.scope["url_route"]["kwargs"].get("skill_level", 5))
        await self.engine.configure({"Skill Level": skill_level})

    async def disconnect(self, code):
        if self.engine is not None:
            await self.engine.quit()

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error(message="Formato JSON inválido", close_code=WSErrorCodes.INVALID_JSON)
            return

        action = data.get("action")

        if action == "move":
            user_uci = data.get("move")
            try:
                user_move = chess.Move.from_uci(user_uci)
            except (ValueError, TypeError):
                await self.send_error(message="Movimiento inválido", close_code=WSErrorCodes.INVALID_JSON)
                return

            if user_move in self.board.legal_moves:
                user_san_string = self.board.san(user_move)

                self.board.push(user_move)

                await self.send(text_data=json.dumps(
                    {
                        "action": "move_confirmed",
                        "move": user_uci,
                        "san": user_san_string,
                        "fen": self.board.fen()
                    }
                ))

                if self.board.is_game_over():
                    await self._handle_game_over()
                    return

                result = await self.engine.play(self.board, chess.engine.Limit(time=0.5))
                ai_move = result.move

                if ai_move in self.board.legal_moves:
                    ai_san_string = self.board.san(ai_move)

                    self.board.push(ai_move)

                    await self.send(text_data=json.dumps(
                        {
                            "action": "ai_move",
                            "move": ai_move.uci(),
                            "san": ai_san_string,
                            "fen": self.board.fen()
                        }
                    ))

    async def _handle_game_over(self):
        await self.send(text_data=json.dumps({
            "action": "game_ended",
            "result": self.board.result()
        }))
