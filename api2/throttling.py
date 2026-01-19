# api2/throttling.py
from rest_framework.throttling import SimpleRateThrottle
from django.core.cache import cache
import time

class UploadRateThrottle(SimpleRateThrottle):
    """
    Throttle específico para endpoints de upload.
    Más restrictivo que el throttle general de usuario.
    """
    scope = 'uploads'
    
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"upload_user_{request.user.id}"
        else:
            ident = self.get_ident(request)
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
    
    def allow_request(self, request, view):
        """
        Permite el request si no se ha excedido el rate limit.
        """
        if request.method != 'POST':
            # Solo throttlear POST requests (uploads)
            return True
        
        # Verificar si es un endpoint de upload
        if not any(path in request.path for path in ['/upload/', '/api/upload/']):
            return True
        
        return super().allow_request(request, view)


class StreamingRateThrottle(SimpleRateThrottle):
    """
    Throttle para endpoints de streaming.
    Más permisivo que uploads pero con límites.
    """
    scope = 'streaming'
    
    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"stream_user_{request.user.id}"
        else:
            ident = self.get_ident(request)
        
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class BurstRateThrottle(SimpleRateThrottle):
    """
    Throttle para prevenir bursts de requests.
    """
    scope = 'burst'
    
    def allow_request(self, request, view):
        """
        Permite bursts pequeños pero limita ráfagas largas.
        """
        key = f"burst_{self.get_ident(request)}_{int(time.time() / 60)}"
        
        # Contar requests en la última ventana de tiempo
        count = cache.get(key, 0)
        
        if count >= 60:  # Máximo 60 requests por minuto
            return False
        
        cache.set(key, count + 1, 65)  # Cache por 65 segundos
        return True