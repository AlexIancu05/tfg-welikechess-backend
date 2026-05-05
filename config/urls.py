from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.views import verify_master_password

urlpatterns = [
    path("", RedirectView.as_view(url='/admin/', permanent=False)),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/users/", include("users.api.urls")),
    path("api/games/", include("games.api.urls")),
    path("api/chat/", include("chat.api.urls")),
    path("api/core/verify-master-password", verify_master_password, name="verify-master-password")
]
