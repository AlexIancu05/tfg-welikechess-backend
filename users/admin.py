from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Esto se ve en el menu como tal, para poder hacer click
    list_display = ('username', 'email', 'is_active', 'date_joined')

    # Por estos se puede buscar un usuario
    search_fields = ('username', 'email')

    # Agrupaciones para que se vea mas bonito
    fieldsets = (
        ('Inicio Sesión', {'fields': ('email', 'username', 'password')}),
        ('Elo', {'fields': ('elo_blitz', 'elo_rapid', 'elo_bullet')}),
        ('Perfil', {'fields': ('avatar', 'friends')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )