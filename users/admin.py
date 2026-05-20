from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, FriendRequest


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'date_joined')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'is_staff', 'is_superuser') 
    
    fieldsets = (
        ('Inicio Sesión', {'fields': ('email', 'username', 'password')}),
        ('Elo', {'fields': ('elo_blitz', 'elo_rapid', 'elo_bullet')}),
        ('Perfil', {'fields': ('avatar', 'friends', 'last_seen')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    filter_horizontal = ('friends',) 


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('sender__username', 'receiver__username') 
    raw_id_fields = ('sender', 'receiver')