# api2/middleware/celery_middleware.py
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from api2.utils.celery_health import CeleryHealth

logger = logging.getLogger(__name__)

class CeleryHealthMiddleware(MiddlewareMixin):
    """
    Middleware que verifica que Celery esté vivo
    antes de permitir operaciones críticas.
    """
    
    # Endpoints que dependen de Celery
    CELERY_DEPENDENT_PATHS = [
        '/api/upload/direct/confirm/',
        '/api/upload/admin/cleanup/',
    ]
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Solo verificar métodos POST/PUT/DELETE que dependen de Celery
        if request.method not in ['POST', 'PUT', 'DELETE']:
            return None
        
        # Verificar si es un endpoint que depende de Celery
        for path in self.CELERY_DEPENDENT_PATHS:
            if request.path.startswith(path):
                can_process, error_info = CeleryHealth.can_process_uploads()
                
                if not can_process:
                    logger.warning(
                        f"Blocked request to {request.path} - Celery unavailable: "
                        f"{error_info.get('code', 'UNKNOWN')}"
                    )
                    
                    return JsonResponse(
                        {
                            'error': error_info.get('error', 'service_unavailable'),
                            'message': error_info.get('message', 'Service temporarily unavailable'),
                            'code': error_info.get('code', 'UNKNOWN'),
                            'timestamp': request.timestamp if hasattr(request, 'timestamp') else None,
                        },
                        status=503  # Service Unavailable
                    )
                
                break
        
        return None