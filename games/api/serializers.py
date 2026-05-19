from django.contrib.auth import get_user_model
from rest_framework import serializers

from games.models import Game, Puzzle, PuzzleAttempt


class PlayerSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "elo_blitz",
            "elo_rapid",
            "elo_bullet",
        ]


class GameListSerializer(serializers.ModelSerializer):
    white_username = serializers.CharField(source="white_player.username", read_only=True)
    black_username = serializers.CharField(source="black_player.username", read_only=True)
    winner_username = serializers.CharField(source="winner.username", read_only=True, allow_null=True)
    
    class Meta:
        model = Game
        fields = [
            "id",
            "mode",
            "status",
            "result",
            "created_at",
            "white_username",
            "black_username",
            "winner_username"
        ]


class GameDetailSerializer(serializers.ModelSerializer):
    white_player = PlayerSimpleSerializer(read_only=True)
    black_player = PlayerSimpleSerializer(read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id",
            "white_player",
            "black_player",
            "winner",
            "status",
            "mode",
            "initial_time",
            "increment",
            "ranked",
            "current_fen",
            "pgn",
            "result",
            "termination_reason",
            "white_elo_change",
            "black_elo_change",
            "created_at",
            "finished_at",
            "duration"
        ]

    def get_duration(self, obj):
        if obj.finished_at:
            return (obj.finished_at - obj.created_at).total_seconds()
        return None


class GameTotalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = "__all__"

class PuzzleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puzzle
        fields = ["lichess_id", "rating", "themes", "fen"]

class PuzzleAttemptSerializer(serializers.ModelSerializer):
    puzzle = PuzzleSerializer(read_only=True)

    class Meta:
        model = PuzzleAttempt
        fields = ["puzzle", "successful", "created_at"]