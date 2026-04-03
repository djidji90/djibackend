# wallet/monitoring/middleware.py
"""
Middleware para monitoreo y logging
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin
from .metrics import API_LATENCY, ERRORS_TOTAL, ACTIVE_USERS

logger = logging.getLogger(__name__)


class MonitoringMiddleware(MiddlewareMixin):
    """Middleware para monitoreo de requests"""
    
    def process_request(self, request):
        request.start_time = time.time()
    
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            
            # Registrar latencia
            endpoint = request.path
            method = request.method
            
            API_LATENCY.labels(endpoint=endpoint, method=method).observe(duration)
            
            # Log para requests lentos
            if duration > 1.0:
                logger.warning(
                    f"Slow request: {method} {endpoint} took {duration:.2f}s",
                    extra={
                        'user_id': request.user.id if request.user.is_authenticated else None,
                        'duration': duration,
                        'status': response.status_code
                    }
                )
        
        return response
    
    def process_exception(self, request, exception):
        # Registrar error
        endpoint = request.path
        error_type = type(exception).__name__
        
        ERRORS_TOTAL.labels(error_type=error_type, endpoint=endpoint).inc()
        
        logger.error(
            f"Error en {endpoint}: {error_type} - {str(exception)}",
            extra={
                'user_id': request.user.id if request.user.is_authenticated else None,
                'error': str(exception)
            }
        )