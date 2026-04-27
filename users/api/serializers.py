from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

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
    (UNFINISHED)
    """

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "avatar",
            "elo_blitz",
            "elo_rapid",
            "elo_bullet",
            "date_joined"
        ]
        # TODO: Añadir historial

class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer para ver su propia información de usuario
    """

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
            "date_joined"
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