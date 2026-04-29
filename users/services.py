import requests
from django.core.cache import cache
from django.db import transaction
from rest_framework import status

from users.models import User, FriendRequest

def get_external_ranking(perf_type="blitz"):
    """
    Obtiene el Top 50 de Lichess y asigna avatares locales.
    """
    valid_types = ["bullet", "blitz", "rapid", "classical"]
    if perf_type not in valid_types:
        perf_type = "blitz"

    cache_key = f"lichess_ranking_{perf_type}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    try:
        local_avatars = [
            "b_bishop_avatar.png", "b_horse_avatar.png", "b_king_avatar.png",
            "b_pawn_avatar.png", "b_queen_avatar.png", "b_rook_avatar.png",
            "w_bishop_avatar.png", "w_horse_avatar.png", "w_king_avatar.png",
            "w_pawn_avatar.png", "w_queen_avatar.png", "w_rook_avatar.png"
        ]

        url = f"https://lichess.org/api/player/top/50/{perf_type}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "WeLikeChess school project / alexiancu1306@gmail.com"
        }
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        users = data.get("users", [])

        formatted_data = [{
            "id": u['id'],
            "name": u['username'].upper(),
            "elo": u['perfs'].get(perf_type, {}).get('rating', 0),
            "tier": u.get('title', 'GM'),
            "online": u.get('online', False),
            "wins": u.get('count', {}).get('all', 0),
            "avatar": local_avatars[len(u['username']) % len(local_avatars)]
        } for u in users]

        cache.set(cache_key, formatted_data, 300)

        return formatted_data
    except Exception:
        print(f"Error sync Lichess: {Exception}")
        return []

class UserService:
    @staticmethod
    @transaction.atomic
    def create_user(email: str, username: str, password: str) -> User:
        """
        Crea y devuelve un usuario
        @transaction.atomic asegura que si algo falla, no se guarde basura en la DB.
        :param email: Email de usuario (SE UTILIZARÁ PARA EL INICIO DE SESIÓN Y NO EL NOMBRE)
        :param username: Nombre de usuario (NO SE UTILIZA PARA INICIAR SESION)
        :param password: Contraseña sin hashear
        :return: Usuario ya creado en BBDD
        """

        user = User.objects.create_user(
            email=email,
            username=username,
            password=password
        )

        return user

    @staticmethod
    def find_by_username(username):
        """
        Busca y devuelve un usuario por su username.
        Devuelve None si no lo encuentra.
        """
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

class FriendService:
    @staticmethod
    def send_friend_request(sender, receiver):
        """
        Procesa el envío de una petición de amistad con todas sus validaciones.
        Devuelve: (success, detail_message, http_status)
        """
        if sender == receiver:
            return False, "No puedes enviarte una solicitud de amistad a ti mismo.", status.HTTP_400_BAD_REQUEST

        if sender.friends.filter(id=receiver.id).exists():
            return False, "Ya sois amigos.", status.HTTP_400_BAD_REQUEST

        if FriendRequest.objects.filter(sender=sender, receiver=receiver, is_active=True).exists():
            return False, "Ya has enviado una solicitud a este usuario.", status.HTTP_400_BAD_REQUEST

        if FriendRequest.objects.filter(sender=receiver, receiver=sender, is_active=True).exists():
            return False, "Este usuario ya te ha enviado una solicitud. Ve a pendientes para aceptarla.", status.HTTP_400_BAD_REQUEST

        existing_request = FriendRequest.objects.filter(sender=sender, receiver=receiver).first()
        if existing_request:
            existing_request.is_active = True
            existing_request.save()
        else:
            FriendRequest.objects.create(sender=sender, receiver=receiver)

        return True, "Solicitud enviada correctamente.", status.HTTP_201_CREATED

    @staticmethod
    def respond_request(sender, receiver, action_type):
        """
        Procesa la respuesta (accept/reject) a una petición pendiente.
        Devuelve: (success, detail_message, http_status)
        """
        friend_request = FriendRequest.objects.filter(sender=sender, receiver=receiver, is_active=True).first()

        if not friend_request:
            return False, "No hay ninguna solicitud pentiende de este usuario", status.HTTP_404_NOT_FOUND

        if action_type == "accept":
            friend_request.is_active = False
            friend_request.save()

            receiver.friends.add(sender)
            return True, "Solicitud aceptada", status.HTTP_200_OK
        elif action_type == "reject":
            friend_request.is_active = False
            friend_request.save()
            return True, "Solicitud rechazada", status.HTTP_200_OK
        else:
            return False, "Acción inválida. Usa 'accept' o 'reject'.", status.HTTP_400_BAD_REQUEST

    @staticmethod
    def remove_friend(user1: User, user2: User):
        if user1 == user2:
            return False, "No puedes eliminarte a ti mismo de tu lista de amigos.", status.HTTP_400_BAD_REQUEST

        if not user1.friends.filter(id=user2.id).exists():
            return False, "Este usuario no está en tu lista de amigos.", status.HTTP_400_BAD_REQUEST

        user1.friends.remove(user2)

        return True, "Amigo eliminado correctamente", status.HTTP_200_OK
