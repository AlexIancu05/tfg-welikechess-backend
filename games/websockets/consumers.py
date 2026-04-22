import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from games.models import Game
from games.services import MatchmakingService

class MatchmakingConsumer(WebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket_group_name = None

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
            self.send(text_data=json.dumps({"error": "Formato JSON invalido"}))
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
                self.send(text_data=json.dumps(
                    {
                        "type": "error",
                        "message": "No puedes jugar contra ti mismo."
                    }
                ))
            else:
                self.send(text_data=json.dumps({"error": f"Estado desconocido: {status}"}))
        else:
            self.send(text_data=json.dumps({"error": "Accion desconocida"}))

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

    def connect(self):
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        self.room_group_name = f"game{self.game_id}"

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )

        self.accept()

        self.send(text_data=json.dumps(
            {
                "type": "system_message",
                "message": "Connection Established"
            }
        ))

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data = None, bytes_data = None):
        text_data_json = json.loads(text_data)
        move = text_data_json.get("move")

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "game_move",
                "move": move
            }
        )

    def game_move(self, event):
        move = event["move"]
        self.send(text_data=json.dumps(
            {
                "type": "game_move",
                "move": move
            }
        ))