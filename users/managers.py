from django.contrib.auth.models import BaseUserManager

class CustomUserManager(BaseUserManager):
    """
    Manager personalizado
    """

    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("El usuario debe tener una dirección de correo electrónico")
        if not username:
            raise ValueError("El usuario debe tener un nombre de usuario")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)

        user.set_password(password)
        user.save(using = self.db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("El Superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El Superusuario debe tener is_superuser=True.")

        return self.create_user(email, username, password, **extra_fields)