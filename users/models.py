import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from users.managers import CustomUserManager


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, max_length=256)
    username = models.CharField(unique=True, max_length=50)

    avatar = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default="/avatars/b_king_avatar.png"
    )

    elo_blitz = models.IntegerField(default=1200)
    elo_rapid = models.IntegerField(default=1200)
    elo_bullet = models.IntegerField(default=1200)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    friends = models.ManyToManyField("self", blank=True, symmetrical=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        indexes = [
            #Busqueda de partida mas rapida
            models.Index(fields=['is_active']),
            #Ranking
            models.Index(fields=['elo_blitz']),
            models.Index(fields=['elo_rapid']),
            models.Index(fields=['elo_bullet']),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="username_case_insensitive_unique"
            )
        ]
    def __str__(self):
        return f"{self.username}"

class FriendRequest(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_friend_requests"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_friend_requests"
    )
    is_active = models.BooleanField(default=True, help_text="False si fue aceptada o rechazada")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["sender", "receiver"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username} ({'Pendiente' if self.is_active else 'Resuelta'})"