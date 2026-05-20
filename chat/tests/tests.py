import json
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username, **kwargs):
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        email=f"{username}@test.com",
        **kwargs,
    )
    return user


def make_friends(user1, user2):
    """Hace que dos usuarios sean amigos mutuamente."""
    user1.friends.add(user2)
    user2.friends.add(user1)


def make_room(user1, user2):
    from chat.models import PrivateChatRoom
    return PrivateChatRoom.objects.create(user1=user1, user2=user2)


def make_message(room, sender, text="Hola"):
    from chat.models import PrivateMessage
    return PrivateMessage.objects.create(room=room, sender=sender, text=text)


# ===========================================================================
# SERIALIZER TESTS
# ===========================================================================

class PrivateMessageSerializerTest(TestCase):
    def setUp(self):
        self.user1 = make_user("msg_u1")
        self.user2 = make_user("msg_u2")
        self.room = make_room(self.user1, self.user2)
        self.message = make_message(self.room, self.user1, "Test message")

    def test_fields_present(self):
        from chat.api.serializers import PrivateMessageSerializer
        data = PrivateMessageSerializer(self.message).data
        for field in ("id", "sender_username", "text", "is_read", "created_at"):
            self.assertIn(field, data)

    def test_sender_username(self):
        from chat.api.serializers import PrivateMessageSerializer
        data = PrivateMessageSerializer(self.message).data
        self.assertEqual(data["sender_username"], "msg_u1")

    def test_text_value(self):
        from chat.api.serializers import PrivateMessageSerializer
        data = PrivateMessageSerializer(self.message).data
        self.assertEqual(data["text"], "Test message")

    def test_is_read_default_false(self):
        from chat.api.serializers import PrivateMessageSerializer
        data = PrivateMessageSerializer(self.message).data
        self.assertFalse(data["is_read"])


class PrivateChatRoomSerializerTest(TestCase):
    def setUp(self):
        self.user1 = make_user("room_u1")
        self.user2 = make_user("room_u2")
        self.room = make_room(self.user1, self.user2)

    def _get_serializer(self, room, request_user):
        from chat.api.serializers import PrivateChatRoomSerializer
        # Simular request con el usuario autenticado
        mock_request = MagicMock()
        mock_request.user = request_user
        return PrivateChatRoomSerializer(room, context={"request": mock_request})

    def test_fields_present(self):
        data = self._get_serializer(self.room, self.user1).data
        for field in ("id", "other_user", "last_message", "last_message_at"):
            self.assertIn(field, data)

    def test_other_user_from_user1_perspective(self):
        data = self._get_serializer(self.room, self.user1).data
        self.assertEqual(data["other_user"]["username"], "room_u2")

    def test_other_user_from_user2_perspective(self):
        data = self._get_serializer(self.room, self.user2).data
        self.assertEqual(data["other_user"]["username"], "room_u1")

    def test_last_message_none_when_no_messages(self):
        data = self._get_serializer(self.room, self.user1).data
        self.assertIsNone(data["last_message"])

    def test_last_message_populated(self):
        make_message(self.room, self.user1, "Último mensaje")
        data = self._get_serializer(self.room, self.user1).data
        self.assertIsNotNone(data["last_message"])
        self.assertEqual(data["last_message"]["text"], "Último mensaje")

    def test_last_message_is_most_recent(self):
        make_message(self.room, self.user1, "Primero")
        make_message(self.room, self.user2, "Segundo")
        data = self._get_serializer(self.room, self.user1).data
        self.assertEqual(data["last_message"]["text"], "Segundo")


# ===========================================================================
# ChatService TESTS
# ===========================================================================

class ChatServiceJoinRoomTest(TestCase):
    def setUp(self):
        self.user1 = make_user("svc_u1")
        self.user2 = make_user("svc_u2")
        make_friends(self.user1, self.user2)

    def test_creates_room_when_none_exists(self):
        from chat.services import ChatService
        room, msg, code = ChatService.join_room(self.user1, self.user2)
        self.assertEqual(code, status.HTTP_200_OK)
        self.assertIsNotNone(room)

    def test_reuses_existing_room(self):
        from chat.services import ChatService
        room1, _, _ = ChatService.join_room(self.user1, self.user2)
        room2, _, _ = ChatService.join_room(self.user1, self.user2)
        self.assertEqual(room1.id, room2.id)

    def test_reuses_room_regardless_of_order(self):
        """La sala es la misma aunque user1/user2 se intercambien."""
        from chat.services import ChatService
        room1, _, _ = ChatService.join_room(self.user1, self.user2)
        room2, _, _ = ChatService.join_room(self.user2, self.user1)
        self.assertEqual(room1.id, room2.id)

    def test_cannot_chat_with_self(self):
        from chat.services import ChatService
        room, msg, code = ChatService.join_room(self.user1, self.user1)
        self.assertIsNone(room)
        self.assertEqual(code, status.HTTP_400_BAD_REQUEST)

    def test_requires_friendship(self):
        from chat.services import ChatService
        stranger = make_user("stranger")
        room, msg, code = ChatService.join_room(self.user1, stranger)
        self.assertIsNone(room)
        self.assertEqual(code, status.HTTP_403_FORBIDDEN)


class ChatServiceFindChatsTest(TestCase):
    def setUp(self):
        self.user = make_user("finder")
        self.other1 = make_user("other_f1")
        self.other2 = make_user("other_f2")
        make_room(self.user, self.other1)
        make_room(self.other2, self.user)  # user es user2 aquí

    def test_finds_rooms_as_user1(self):
        from chat.services import ChatService
        rooms = ChatService.find_user_chats(self.user)
        self.assertEqual(rooms.count(), 2)

    def test_does_not_return_unrelated_rooms(self):
        from chat.services import ChatService
        unrelated1 = make_user("unrel1")
        unrelated2 = make_user("unrel2")
        make_room(unrelated1, unrelated2)
        rooms = ChatService.find_user_chats(self.user)
        self.assertEqual(rooms.count(), 2)

    def test_empty_when_no_rooms(self):
        from chat.services import ChatService
        lonely = make_user("lonely")
        rooms = ChatService.find_user_chats(lonely)
        self.assertEqual(rooms.count(), 0)


# ===========================================================================
# ChatRoomViewSet API TESTS
# ===========================================================================

class ChatRoomViewSetListTest(APITestCase):
    def setUp(self):
        self.user = make_user("api_chat_u1")
        self.other = make_user("api_chat_u2")
        self.room = make_room(self.user, self.other)
        self.client.force_authenticate(user=self.user)

    def test_list_returns_own_rooms(self):
        response = self.client.get("/api/chat/")
        self.assertEqual(response.status_code, 200)
        # Soporta tanto respuesta paginada {"results": [...]} como lista plana
        results = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        ids = [r["id"] for r in results]
        self.assertIn(self.room.id, ids)

    def test_list_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/chat/")
        self.assertEqual(response.status_code, 401)

    def test_list_does_not_include_other_rooms(self):
        u3 = make_user("api_chat_u3")
        u4 = make_user("api_chat_u4")
        make_room(u3, u4)
        response = self.client.get("/api/chat/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        # Todas las salas devueltas deben pertenecer al usuario autenticado
        for room_data in results:
            other = room_data["other_user"]["username"]
            self.assertIn(other, ["api_chat_u2"])


class ChatRoomViewSetStartChatTest(APITestCase):
    def setUp(self):
        self.user = make_user("start_u1")
        self.friend = make_user("start_u2")
        make_friends(self.user, self.friend)
        self.client.force_authenticate(user=self.user)

    def test_start_chat_creates_room(self):
        response = self.client.post(f"/api/chat/start/{self.friend.username}/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("id", response.data)

    def test_start_chat_idempotent(self):
        response1 = self.client.post(f"/api/chat/start/{self.friend.username}/")
        response2 = self.client.post(f"/api/chat/start/{self.friend.username}/")
        self.assertEqual(response1.data["id"], response2.data["id"])

    def test_start_chat_with_non_friend_forbidden(self):
        stranger = make_user("start_stranger")
        response = self.client.post(f"/api/chat/start/{stranger.username}/")
        self.assertEqual(response.status_code, 403)

    def test_start_chat_with_self_bad_request(self):
        response = self.client.post(f"/api/chat/start/{self.user.username}/")
        self.assertEqual(response.status_code, 400)

    def test_start_chat_user_not_found(self):
        response = self.client.post("/api/chat/start/nobody_exists/")
        self.assertIn(response.status_code, (404, 400))


class ChatRoomViewSetHistoryTest(APITestCase):
    def setUp(self):
        self.user1 = make_user("hist_u1")
        self.user2 = make_user("hist_u2")
        self.room = make_room(self.user1, self.user2)
        for i in range(3):
            make_message(self.room, self.user1, f"Mensaje {i}")
        self.client.force_authenticate(user=self.user1)

    def test_history_returns_messages(self):
        response = self.client.get(f"/api/chat/{self.room.id}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)

    def test_history_ordered_oldest_first(self):
        response = self.client.get(f"/api/chat/{self.room.id}/history/")
        texts = [m["text"] for m in response.data]
        self.assertEqual(texts, ["Mensaje 0", "Mensaje 1", "Mensaje 2"])

    def test_history_limited_to_50(self):
        for i in range(60):
            make_message(self.room, self.user2, f"Extra {i}")
        response = self.client.get(f"/api/chat/{self.room.id}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data), 50)

    def test_history_forbidden_for_non_member(self):
        outsider = make_user("hist_outsider")
        self.client.force_authenticate(user=outsider)
        response = self.client.get(f"/api/chat/{self.room.id}/history/")
        # get_queryset filtra por usuario, así que get_object() lanza 404
        # antes de llegar a la comprobación explícita de membresía
        self.assertIn(response.status_code, (403, 404))

    def test_history_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/chat/{self.room.id}/history/")
        self.assertEqual(response.status_code, 401)


# ===========================================================================
# PrivateChatConsumer WEBSOCKET TESTS
# ===========================================================================

class PrivateChatConsumerTest(TransactionTestCase):
    """
    Tests del consumer WebSocket de chat privado.
    Usa TransactionTestCase y cierra la conexión DB en tearDown para
    evitar que database_sync_to_async corrompa la conexión del hilo principal.
    """

    def tearDown(self):
        from django.db import connection
        connection.close()

    def _make_communicator(self, user, room_id):
        """Crea un WebsocketCommunicator con el scope correcto."""
        from channels.testing import WebsocketCommunicator
        from chat.websockets.consumers import PrivateChatConsumer

        communicator = WebsocketCommunicator(
            PrivateChatConsumer.as_asgi(),
            f"/ws/chat/{room_id}/",
            headers=[],
        )
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {"kwargs": {"room_id": str(room_id)}}
        return communicator

    # --- Connect ---

    def test_member_can_connect(self):
        user1 = make_user("ws_u1")
        user2 = make_user("ws_u2")
        room = make_room(user1, user2)

        communicator = self._make_communicator(user1, room.id)

        async def run():
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.disconnect()

        async_to_sync(run)()

    def test_non_member_cannot_connect(self):
        user1 = make_user("ws_nm1")
        user2 = make_user("ws_nm2")
        outsider = make_user("ws_out")
        room = make_room(user1, user2)

        communicator = self._make_communicator(outsider, room.id)

        async def run():
            connected, _ = await communicator.connect()
            self.assertFalse(connected)

        async_to_sync(run)()

    def test_unauthenticated_cannot_connect(self):
        user1 = make_user("ws_auth1")
        user2 = make_user("ws_auth2")
        room = make_room(user1, user2)

        communicator = self._make_communicator(AnonymousUser(), room.id)

        async def run():
            connected, _ = await communicator.connect()
            self.assertFalse(connected)

        async_to_sync(run)()

    # --- Send / Receive ---

    def test_send_message_broadcasts_to_sender(self):
        user1 = make_user("ws_send1")
        user2 = make_user("ws_send2")
        room = make_room(user1, user2)

        comm1 = self._make_communicator(user1, room.id)

        async def run():
            connected, _ = await comm1.connect()
            self.assertTrue(connected)

            await comm1.send_json_to({"text": "Hola!"})
            response = await comm1.receive_json_from()

            self.assertEqual(response["text"], "Hola!")
            self.assertEqual(response["sender_username"], "ws_send1")
            await comm1.disconnect()

        async_to_sync(run)()

    def test_send_message_saves_to_db(self):
        from chat.models import PrivateMessage

        user1 = make_user("ws_db1")
        user2 = make_user("ws_db2")
        room = make_room(user1, user2)

        comm = self._make_communicator(user1, room.id)

        async def run():
            await comm.connect()
            await comm.send_json_to({"text": "Guardado"})
            await comm.receive_json_from()  # esperar broadcast
            await comm.disconnect()

        async_to_sync(run)()

        self.assertTrue(PrivateMessage.objects.filter(room=room, text="Guardado").exists())

    def test_message_has_id_and_created_at(self):
        user1 = make_user("ws_meta1")
        user2 = make_user("ws_meta2")
        room = make_room(user1, user2)

        comm = self._make_communicator(user1, room.id)

        async def run():
            await comm.connect()
            await comm.send_json_to({"text": "Meta"})
            response = await comm.receive_json_from()
            self.assertIn("id", response)
            self.assertIn("created_at", response)
            await comm.disconnect()

        async_to_sync(run)()

    def test_invalid_json_does_not_crash(self):
        user1 = make_user("ws_json1")
        user2 = make_user("ws_json2")
        room = make_room(user1, user2)

        comm = self._make_communicator(user1, room.id)

        async def run():
            await comm.connect()
            await comm.send_to(text_data="esto no es json{{{")
            response = await comm.receive_json_from()
            self.assertEqual(response["type"], "error")
            await comm.disconnect()

        async_to_sync(run)()

    def test_two_members_receive_message(self):
        """Ambos miembros de la sala reciben el mensaje enviado por uno."""
        user1 = make_user("ws_two1")
        user2 = make_user("ws_two2")
        room = make_room(user1, user2)

        comm1 = self._make_communicator(user1, room.id)
        comm2 = self._make_communicator(user2, room.id)

        async def run():
            await comm1.connect()
            await comm2.connect()

            await comm1.send_json_to({"text": "Para los dos"})

            resp1 = await comm1.receive_json_from()
            resp2 = await comm2.receive_json_from()

            self.assertEqual(resp1["text"], "Para los dos")
            self.assertEqual(resp2["text"], "Para los dos")

            await comm1.disconnect()
            await comm2.disconnect()

        async_to_sync(run)()

    def test_disconnect_does_not_crash(self):
        user1 = make_user("ws_disc1")
        user2 = make_user("ws_disc2")
        room = make_room(user1, user2)

        comm = self._make_communicator(user1, room.id)

        async def run():
            await comm.connect()
            await comm.disconnect()  # no debe lanzar

        async_to_sync(run)()


# ===========================================================================
# MODEL TESTS
# ===========================================================================

class PrivateChatRoomModelTest(TestCase):
    def setUp(self):
        self.user1 = make_user("model_u1")
        self.user2 = make_user("model_u2")
        self.room = make_room(self.user1, self.user2)

    def test_room_str(self):
        """El __str__ debe incluir los usernames de ambos participantes."""
        s = str(self.room)
        self.assertIn("model_u1", s)
        self.assertIn("model_u2", s)

    def test_last_message_at_set_on_create(self):
        """last_message_at se rellena al crear la sala (auto_now_add o default)."""
        # Solo verificamos que tiene un valor datetime válido
        self.assertIsNotNone(self.room.last_message_at)

    def test_messages_relation(self):
        make_message(self.room, self.user1, "rel test")
        self.assertEqual(self.room.messages.count(), 1)


class PrivateMessageModelTest(TestCase):
    def setUp(self):
        self.user1 = make_user("pmm_u1")
        self.user2 = make_user("pmm_u2")
        self.room = make_room(self.user1, self.user2)

    def test_message_str(self):
        msg = make_message(self.room, self.user1, "Hola mundo")
        s = str(msg)
        self.assertIn("pmm_u1", s)

    def test_is_read_default_false(self):
        msg = make_message(self.room, self.user1)
        self.assertFalse(msg.is_read)

    def test_message_cascade_delete_with_room(self):
        from chat.models import PrivateMessage
        make_message(self.room, self.user1, "borrar")
        room_id = self.room.id
        self.room.delete()
        # Filtrar por PK, no por la instancia eliminada
        self.assertEqual(PrivateMessage.objects.filter(room_id=room_id).count(), 0)