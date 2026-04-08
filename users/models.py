import uuid

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db.models.functions import Lower

from users.managers import CustomUserManager


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, max_length=256)
    username = models.CharField(unique=True, max_length=50)

    elo_blitz = models.IntegerField(default=1200)
    elo_rapid = models.IntegerField(default=1200)
    elo_bullet = models.IntegerField(default=1200)
    elo_classical = models.IntegerField(default=1200)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        indexes = [
            #Busqueda de partida mas rapida
            models.Index(fields=['is_active']),
            #Ranking
            models.Index(fields=['elo_blitz']),
            models.Index(fields=['elo_rapid']),
            models.Index(fields=['elo_bullet']),
            models.Index(fields=['elo_classical']),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="username_case_insensitive_unique"
            )
        ]


    def __str__(self):
        return f"{self.username} ({self.email})"