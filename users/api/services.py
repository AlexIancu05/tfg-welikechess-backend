from users.models import User
from django.db import transaction

@transaction.atomic
def create_user(email: str, username: str, password: str) -> User:
    """
    Crea y devuelve un usuario
    @transaction.atomic asegura que si algo falla, no se guarde basura en la DB.
    :param email: Email de usuario (SE UTILIZARÁ PARA EL INICIO DE SESIÓN Y NO EL NOMBRE
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