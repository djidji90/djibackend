# api2/utils/celery_health.py
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CeleryHealth:
    """Utilidad para verificar la salud de Celery"""
    
    @staticmethod
    def is_alive(max_minutes=5):
        """
        Verifica si Celery está vivo basado en el último heartbeat.
        
        Args:
            max_minutes: Máximo minutos sin heartbeat para considerar muerto
            
        Returns:
            bool: True si está vivo, False si está muerto
        """
        heartbeat = cache.get('celery:heartbeat')
        
        if not heartbeat:
            logger.warning("No Celery heartbeat found")
            return False
        
        try:
            last_beat = datetime.fromisoformat(heartbeat)
            time_since = timezone.now() - last_beat
            
            if time_since > timedelta(minutes=max_minutes):
                logger.error(f"Celery heartbeat too old: {time_since}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error parsing heartbeat: {str(e)}")
            return False
    
    @staticmethod
    def get_health_status():
        """Obtiene estado completo de salud"""
        status = {
            'alive': CeleryHealth.is_alive(),
            'heartbeat': cache.get('celery:heartbeat'),
            'workers': cache.get('celery:worker_count', 0),
            'queue_sizes': cache.get('celery:queue_sizes', {}),
            'system_metrics': cache.get('system:metrics', {}),
            'last_check': timezone.now().isoformat(),
        }
        
        # Determinar severidad
        if not status['alive']:
            status['severity'] = 'critical'
            status['message'] = 'Celery is not responding'
        elif status['workers'] == 0:
            status['severity'] = 'warning'
            status['message'] = 'No active workers detected'
        else:
            status['severity'] = 'healthy'
            status['message'] = 'Celery is operational'
        
        return status
    
    @staticmethod
    def can_process_uploads():
        """
        Determina si el sistema puede aceptar nuevos uploads.
        Usar antes de generar URLs de upload.
        """
        # 1. Verificar que Celery esté vivo
        if not CeleryHealth.is_alive():
            return False, {
                'error': 'system_unavailable',
                'message': 'Processing system is temporarily unavailable',
                'code': 'CELERY_DOWN',
                'estimated_recovery': 'Please try again in 5-10 minutes'
            }
        
        # 2. Verificar que haya workers
        worker_count = cache.get('celery:worker_count', 0)
        if worker_count == 0:
            return False, {
                'error': 'no_workers',
                'message': 'No processing workers available',
                'code': 'NO_WORKERS',
            }
        
        # 3. Verificar cola de uploads no saturada
        queue_sizes = cache.get('celery:queue_sizes', {})
        uploads_pending = queue_sizes.get('uploads', 0)
        
        if uploads_pending > 50:  # Límite configurable
            return False, {
                'error': 'queue_full',
                'message': 'Upload queue is currently full',
                'code': 'QUEUE_FULL',
                'pending_tasks': uploads_pending,
                'suggestion': 'Please try again in a few minutes'
            }
        
        # 4. Verificar métricas del sistema
        metrics = cache.get('system:metrics', {})
        if metrics.get('memory_percent', 0) > 90:
            return False, {
                'error': 'high_memory_usage',
                'message': 'System memory usage is high',
                'code': 'HIGH_MEMORY',
            }
        
        return True, {'message': 'System ready to accept uploads'}