import requests
from django.core.cache import cache

from users.models import User
from django.db import transaction

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