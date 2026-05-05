from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

@api_view(["POST"])
@permission_classes([AllowAny])
def verify_master_password(request):
    """
    Endpoint: POST /api/core/verify-password/
    Recibe: {"password": "la_contraseña"}
    """
    password = request.data.get("password")

    if not password:
        return Response({"valid": False, "message": "Falta la contraseña"}, status=status.HTTP_400_BAD_REQUEST)

    if password == settings.MASTER_PASSWORD:
        return Response({"valid": True}, status=status.HTTP_200_OK)

    return Response({"valid": False, "message": "Contraseña incorrecta"}, status=status.HTTP_401_UNAUTHORIZED)