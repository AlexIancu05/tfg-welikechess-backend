import uuid

import chess
from django.conf import settings
from django.db import models
from django.db.models import Q


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    STATUS_CHOICES = [
        ("waiting", "Esperando rival"),
        ("in_progress", "En curso"),
        ("completed", "Completada"),
    ]

    MODE_CHOICES = [
        ('bullet', 'Bullet'),
        ('blitz', 'Blitz'),
        ('rapid', 'Rapid')
    ]

    RESULT_CHOICES = [
        ("1-0", "Victoria Blancas"),
        ("0-1", "Victoria Negras"),
        ("1/2-1/2", "Tablas"),
        ("*", "En curso")
    ]

    TERMINATION_CHOICES = [
        ('checkmate', 'Jaque Mate'),
        ('timeout', 'Tiempo agotado'),
        ('resignation', 'Abandono'),
        ('disconnected', 'Desconexión'),
        ('draw', 'Tablas'),
    ]

    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="games_as_white"
    )

    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="games_as_black"
    )

    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='games_won'
    )

    #Partida
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='blitz')
    initial_time = models.PositiveIntegerField(default=600)
    increment = models.PositiveIntegerField(default=0)
    #Ranked o Casual
    ranked = models.BooleanField(default=True)

    # Relojes de la partida (segundos)
    white_time_left = models.FloatField(null=True, blank=True)
    black_time_left = models.FloatField(null=True, blank=True)
    last_move_at = models.DateTimeField(null=True, blank=True)

    #Estado del tablero
    current_fen = models.CharField(max_length=120, default=chess.STARTING_FEN)

    #Historial de movimientos
    pgn = models.TextField(blank=True, default="")

    white_elo_change = models.IntegerField(default=0)
    black_elo_change = models.IntegerField(default=0)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default="*")
    termination_reason = models.CharField(max_length=25, choices=TERMINATION_CHOICES, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "mode", "initial_time", "increment", "created_at"],
                name="matchmaking_idx"
            ),
            models.Index(fields=["white_player"]),
            models.Index(fields=["black_player"]),
            models.Index(fields=["winner"])
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(status='completed') | Q(termination_reason__isnull=True),
                name='termination_reason_only_when_completed'
            ),
            models.CheckConstraint(
                check=~Q(white_player=models.F("black_player")),
                name="players_must_be_different"
            )
        ]

    def __str__(self):
        return f"{self.id} - {self.status}"