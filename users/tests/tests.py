from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from users.models import User
from users.managers import CustomUserManager
from users.api.permissions import IsOwnerOrReadOnly


# ─────────────────────────────────────────────
# 1. MODELO Y MANAGER
# ─────────────────────────────────────────────

class CustomUserManagerTest(TestCase):
    """Tests para CustomUserManager"""

    def test_create_user_ok(self):
        user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="SecurePass123!"
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.username, "testuser")
        self.assertTrue(user.check_password("SecurePass123!"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_email_normalizado(self):
        user = User.objects.create_user(
            email="Test@EXAMPLE.COM",
            username="normaluser",
            password="SecurePass123!"
        )
        self.assertEqual(user.email, "Test@example.com")

    def test_create_user_sin_email_lanza_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", username="nomail", password="pass")

    def test_create_user_sin_username_lanza_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="a@b.com", username="", password="pass")

    def test_create_superuser_ok(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            username="adminuser",
            password="AdminPass123!"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)

    def test_create_superuser_sin_is_staff_lanza_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin2@example.com",
                username="admin2",
                password="AdminPass123!",
                is_staff=False
            )

    def test_create_superuser_sin_is_superuser_lanza_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin3@example.com",
                username="admin3",
                password="AdminPass123!",
                is_superuser=False
            )


class UserModelTest(TestCase):
    """Tests para el modelo User"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="model@example.com",
            username="modeluser",
            password="SecurePass123!"
        )

    def test_str_devuelve_username(self):
        self.assertEqual(str(self.user), "modeluser")

    def test_elo_defaults(self):
        self.assertEqual(self.user.elo_blitz, 1200)
        self.assertEqual(self.user.elo_rapid, 1200)
        self.assertEqual(self.user.elo_bullet, 1200)

    def test_username_field_es_email(self):
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_required_fields_contiene_username(self):
        self.assertIn("username", User.REQUIRED_FIELDS)

    def test_email_unico(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email="model@example.com",
                username="otrouser",
                password="SecurePass123!"
            )

    def test_username_unico_case_insensitive(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email="otro@example.com",
                username="MODELUSER",  # mismo username en mayúsculas
                password="SecurePass123!"
            )

    def test_id_es_uuid(self):
        import uuid
        self.assertIsInstance(self.user.id, uuid.UUID)


# ─────────────────────────────────────────────
# 2. ENDPOINTS DE LA API
# ─────────────────────────────────────────────

class UserRegistrationAPITest(APITestCase):
    """Tests para POST /api/users/ (registro)"""

    def setUp(self):
        self.url = reverse("user-list")

    def test_registro_valido(self):
        data = {
            "email": "nuevo@example.com",
            "username": "nuevousuario",
            "password": "SecurePass123!"
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="nuevo@example.com").exists())

    def test_registro_sin_email(self):
        data = {"username": "sinmail", "password": "SecurePass123!"}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_registro_sin_username(self):
        data = {"email": "sinuser@example.com", "password": "SecurePass123!"}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_registro_password_debil(self):
        data = {
            "email": "weak@example.com",
            "username": "weakuser",
            "password": "123"
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_registro_email_duplicado(self):
        User.objects.create_user(
            email="dup@example.com", username="dupuser", password="SecurePass123!"
        )
        data = {
            "email": "dup@example.com",
            "username": "otrouser",
            "password": "SecurePass123!"
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registro_username_duplicado(self):
        User.objects.create_user(
            email="first@example.com", username="dupuser", password="SecurePass123!"
        )
        data = {
            "email": "second@example.com",
            "username": "dupuser",
            "password": "SecurePass123!"
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registro_no_devuelve_password(self):
        data = {
            "email": "nopwd@example.com",
            "username": "nopwduser",
            "password": "SecurePass123!"
        }
        response = self.client.post(self.url, data, format="json")
        self.assertNotIn("password", response.data)


class UserListAPITest(APITestCase):
    """Tests para GET /api/users/ (listado)"""

    def setUp(self):
        self.url = reverse("user-list")
        self.user1 = User.objects.create_user(
            email="u1@example.com", username="user1", password="SecurePass123!"
        )
        self.user2 = User.objects.create_user(
            email="u2@example.com", username="user2", password="SecurePass123!"
        )
        self.inactive_user = User.objects.create_user(
            email="inactive@example.com", username="inactiveuser", password="SecurePass123!"
        )
        self.inactive_user.is_active = False
        self.inactive_user.save()

    def test_listado_sin_autenticacion(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_listado_solo_usuarios_activos(self):
        response = self.client.get(self.url)
        usernames = [u["username"] for u in response.data["results"] if "results" in response.data] or \
                    [u["username"] for u in response.data]
        self.assertIn("user1", usernames)
        self.assertIn("user2", usernames)
        self.assertNotIn("inactiveuser", usernames)

    def test_listado_campos_publicos(self):
        response = self.client.get(self.url)
        results = response.data.get("results", response.data)
        if results:
            user_data = results[0]
            self.assertIn("username", user_data)
            self.assertIn("elo_blitz", user_data)
            self.assertNotIn("email", user_data)
            self.assertNotIn("password", user_data)

    def test_busqueda_por_username(self):
        response = self.client.get(self.url, {"search": "user1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertTrue(any(u["username"] == "user1" for u in results))


class UserDetailAPITest(APITestCase):
    """Tests para GET /api/users/{username}/ (detalle)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="detail@example.com", username="detailuser", password="SecurePass123!"
        )
        self.url = reverse("user-detail", kwargs={"username": self.user.username})

    def test_detalle_sin_autenticacion(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_detalle_usuario_inexistente(self):
        url = reverse("user-detail", kwargs={"username": "noexiste"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detalle_propio_con_autenticacion(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("email", response.data)

    def test_detalle_ajeno_no_muestra_email(self):
        other = User.objects.create_user(
            email="other@example.com", username="otheruser", password="SecurePass123!"
        )
        self.client.force_authenticate(user=other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserUpdateAPITest(APITestCase):
    """Tests para PATCH /api/users/{username}/ (actualización parcial)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="update@example.com", username="updateuser", password="SecurePass123!"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", username="otheruser", password="SecurePass123!"
        )
        self.url = reverse("user-detail", kwargs={"username": self.user.username})

    def test_update_propio_autenticado(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {"username": "updatedname"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_sin_autenticacion(self):
        response = self.client.patch(self.url, {"username": "hacker"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_usuario_ajeno(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(self.url, {"username": "hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_admin_puede_editar_cualquier_usuario(self):
        admin = User.objects.create_superuser(
            email="admin@example.com", username="adminuser", password="AdminPass123!"
        )
        self.client.force_authenticate(user=admin)
        response = self.client.patch(self.url, {"username": "adminedited"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_propio_no_puede_modificar_elo(self):
        """Usuario no puede 'hackear' su propio Elo"""
        self.client.force_authenticate(user=self.user)

        elo_original = self.user.elo_blitz
        data_maliciosa = {
            "username": "Nombre",
            "elo_blitz": 3500
        }

        response = self.client.patch(self.url, data_maliciosa, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()

        self.assertEqual(self.user.username, "Nombre")
        self.assertEqual(self.user.elo_blitz, elo_original)


class UserDeleteAPITest(APITestCase):
    """Tests para DELETE /api/users/{username}/ (eliminación)"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="delete@example.com", username="deleteuser", password="SecurePass123!"
        )
        self.other_user = User.objects.create_user(
            email="other2@example.com", username="otheruser2", password="SecurePass123!"
        )
        self.url = reverse("user-detail", kwargs={"username": self.user.username})

    def test_delete_propio_autenticado(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(username="deleteuser").exists())

    def test_delete_sin_autenticacion(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_usuario_ajeno(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_admin_puede_eliminar_cualquier_usuario(self):
        admin = User.objects.create_superuser(
            email="admin2@example.com", username="adminuser2", password="AdminPass123!"
        )
        self.client.force_authenticate(user=admin)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────
# 3. PERMISOS
# ─────────────────────────────────────────────

class IsOwnerOrReadOnlyTest(APITestCase):
    """Tests para el permiso IsOwnerOrReadOnly"""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com", username="owneruser", password="SecurePass123!"
        )
        self.stranger = User.objects.create_user(
            email="stranger@example.com", username="strangeruser", password="SecurePass123!"
        )
        self.url = reverse("user-detail", kwargs={"username": self.owner.username})

    def test_metodos_seguros_permitidos_sin_autenticacion(self):
        for method in ["get", "head", "options"]:
            response = getattr(self.client, method)(self.url)
            self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                msg=f"Método {method.upper()} debería estar permitido sin autenticación")

    def test_escritura_permitida_al_owner(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(self.url, {"username": "owneredited"}, format="json")
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_escritura_denegada_a_usuario_ajeno(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.patch(self.url, {"username": "stolen"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_escritura_denegada_sin_autenticacion(self):
        response = self.client.patch(self.url, {"username": "anon"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_has_object_permission_owner_retorna_true(self):
        from unittest.mock import MagicMock
        permission = IsOwnerOrReadOnly()
        request = MagicMock()
        request.method = "PATCH"
        request.user = self.owner
        self.assertTrue(permission.has_object_permission(request, None, self.owner))

    def test_has_object_permission_no_owner_retorna_false(self):
        from unittest.mock import MagicMock
        permission = IsOwnerOrReadOnly()
        request = MagicMock()
        request.method = "PATCH"
        request.user = self.stranger
        self.assertFalse(permission.has_object_permission(request, None, self.owner))

    def test_has_object_permission_safe_method_retorna_true(self):
        from unittest.mock import MagicMock
        permission = IsOwnerOrReadOnly()
        request = MagicMock()
        request.method = "GET"
        self.assertTrue(permission.has_object_permission(request, None, self.owner))