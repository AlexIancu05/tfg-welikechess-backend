from django.contrib import admin
from .models import Game, GameMessage, Puzzle, PuzzleAttempt, GameChallenge


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'white_player', 'black_player', 'status', 'mode', 'ranked', 'created_at')
    list_filter = ('status', 'mode', 'ranked', 'termination_reason', 'created_at')
    search_fields = ('id', 'white_player__username', 'black_player__username')
    raw_id_fields = ('white_player', 'black_player', 'winner')
    readonly_fields = ('id', 'created_at', 'finished_at')


@admin.register(GameMessage)
class GameMessageAdmin(admin.ModelAdmin):
    list_display = ('game', 'sender', 'text_preview', 'created_at')
    search_fields = ('game__id', 'sender__username', 'text')
    raw_id_fields = ('game', 'sender')

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Mensaje'


@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    list_display = ('lichess_id', 'rating', 'themes_preview')
    search_fields = ('lichess_id', 'themes')
    
    def themes_preview(self, obj):
        return obj.themes[:50] + '...' if len(obj.themes) > 50 else obj.themes
    themes_preview.short_description = 'Temas'


@admin.register(PuzzleAttempt)
class PuzzleAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'puzzle', 'successful', 'created_at')
    list_filter = ('successful', 'created_at')
    search_fields = ('user__username', 'puzzle__lichess_id')
    raw_id_fields = ('user', 'puzzle')


@admin.register(GameChallenge)
class GameChallengeAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'mode', 'initial_time', 'created_at')
    list_filter = ('status', 'mode', 'created_at')
    search_fields = ('sender__username', 'receiver__username')
    raw_id_fields = ('sender', 'receiver')