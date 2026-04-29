from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from games.services import GameService
from users import services
from users.models import User


class UserSerializerComplete(serializers.ModelSerializer):
    """
    SERIALIZADOR SOLO PARA TESTING
    """

    class Meta:
        model = User
        fields = "__all__"


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer para el registro (POST)
    """
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )

    class Meta:
        model = User
        fields = ["email", "username", "password"]

    def create(self, validated_data):
        return services.create_user(**validated_data)


class UserPublicSerializer(serializers.ModelSerializer):
    """
    Serializer para listar usuarios y ver perfiles ajenos (GET)
    """

    friends = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field="username"
    )

    recent_games = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "avatar",
            "elo_blitz",
            "elo_rapid",
            "elo_bullet",
            "date_joined",
            "friends",
            "recent_games"
        ]

    def get_recent_games(self, user):
        """
        Obtiene las ultimas 10 partidas acabadas del usuario
        """
        return GameService.find_user_recent_games(user, limit=10)


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer para ver su propia información de usuario
    """

    friends = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field='username'
    )

    recent_games = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "avatar",
            "elo_blitz",
            "elo_rapid",
            "elo_bullet",
            "is_active",
            "date_joined",
            "friends",
            "recent_games"
        ]

        read_only_fields = [
            "id",
            "email",
            "elo_blitz",
            "elo_rapid",
            "elo_bullet",
            "is_active",
            "date_joined"
        ]

    def get_recent_games(self, user):
        """
        Obtiene las ultimas 10 partidas acabadas del usuario
        """
        return GameService.find_user_recent_games(user, limit=10)


from users.models import FriendRequest


class PendingFriendRequestSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_avatar = serializers.CharField(source='sender.avatar', read_only=True)

    class Meta:
        model = FriendRequest
        fields = ['sender_username', 'sender_avatar', 'created_at']
