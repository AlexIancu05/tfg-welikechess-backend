import json

import chess
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from games.models import Game
from games.services import MatchmakingService, GameService
from games.websockets.constants import WSErrorCodes


class MatchmakingConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket_group_name = None

    def send_error(self, message: str, close_connection: bool = False, close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
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
        if self.scope["user"].is_authenticated:
            Game.objects.filter(
                white_player=self.scope["user"],
                status="waiting"
            ).delete()

    def receive(self, text_data = None, bytes_data = None):
        if text_data is None:
            return

        try:
            text_data_json = json.loads(text_data)
        except Exception:
            self.send_error(message="Formato JSON inválido", close_code=WSErrorCodes.INVALID_JSON)
            return

        action = text_data_json.get("action")
        game_mode = text_data_json.get("mode")
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
        super().__init__(args, kwargs)
        self.game_id = None
        self.room_group_name = None
        self.game = None

    def send_error(self, message: str, close_connection: bool = False, close_code: WSErrorCodes = WSErrorCodes.GENERIC_ERROR):
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

    def connect(self):
        user = self.scope["user"]
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        self.room_group_name = f"game{self.game_id}"

        self.accept()

        # Control de seguridad del usuario, si no esta autenticado, se cierra el Websocket
        if not user.is_authenticated:
            self.send_error(message="Usuario no autenticado", close_connection=True, close_code=WSErrorCodes.UNAUTHENTICATED)
            return

        # Cargar partida
        try:
            self.game = Game.objects.get(id=self.game_id)
        except ObjectDoesNotExist:
            self.send_error(message="Partida no encontrada", close_connection=True, close_code=WSErrorCodes.GAME_NOT_FOUND)
            return

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.send(json.dumps(
            {
                "type": "game_state",
                "fen": self.game.current_fen,
                "status": self.game.status
            }
        ))

    def disconnect(self, code):
        if self.room_group_name:
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name,
                self.channel_name
            )

    def receive(self, text_data = None, bytes_data = None):
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
        else:
            self.send_error(message=f"Acción desconocida: '{action}'", close_code=WSErrorCodes.GENERIC_ERROR)
            
    def handle_move(self, move_uci):
        """Procesa un movimiento en formato UCI. EJ: e2e4"""
        self.game.refresh_from_db()

        success, result_data, error_code = GameService.process_move(self.game, self.scope["user"], move_uci)

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
            "result": event["result"]
        }))