from django.utils.deprecation import MiddlewareMixin
from django.utils.timezone import now
from django.core.cache import cache
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

class UpdateLastSeenMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.path.startswith('/api/') or request.path.startswith('/api/login/'):
            return

        jwt_auth = JWTAuthentication()
        try:
            auth_result = jwt_auth.authenticate(request)
        except (InvalidToken, AuthenticationFailed):
            auth_result = None

        if auth_result:
            user, token = auth_result
            
            cache_key = f"last_seen_{user.id}"
            
            if not cache.get(cache_key):
                user.last_seen = now()
                user.save(update_fields=['last_seen'])
                
                cache.set(cache_key, True, 300)