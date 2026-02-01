# api2/tasks/monitoring_tasks.py
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
import logging
import psutil
import os

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    queue='monitoring',
    max_retries=3,
    default_retry_delay=60
)
def celery_heartbeat(self):
    """
    Heartbeat para monitorear que Celery está vivo.
    Se ejecuta cada 5 minutos.
    """
    try:
        timestamp = timezone.now().isoformat()
        
        # Guardar heartbeat en cache
        cache.set('celery:heartbeat', timestamp, timeout=300)  # 5 minutos
        
        # Métricas del sistema
        system_metrics = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
        }
        
        # Guardar métricas
        cache.set('system:metrics', system_metrics, timeout=300)
        
        # Contador de ejecuciones (para monitoreo)
        heartbeat_count = cache.get('celery:heartbeat_count', 0) + 1
        cache.set('celery:heartbeat_count', heartbeat_count, timeout=86400)
        
        logger.debug(f"Heartbeat #{heartbeat_count} - {timestamp}")
        
        return {
            'status': 'healthy',
            'timestamp': timestamp,
            'service': 'celery',
            'metrics': system_metrics,
            'heartbeat_count': heartbeat_count,
        }
        
    except Exception as e:
        logger.error(f"Heartbeat failed: {str(e)}")
        # No reintentar inmediatamente para no saturar
        raise self.retry(exc=e, countdown=300)  # Reintentar en 5 minutos

@shared_task(queue='monitoring')
def check_celery_workers():
    """Verifica que haya workers activos"""
    from celery import current_app
    
    try:
        inspector = current_app.control.inspect()
        
        if not inspector:
            return {'status': 'error', 'message': 'No inspector available'}
        
        active_workers = inspector.active() or {}
        registered_tasks = inspector.registered() or {}
        
        worker_count = len(active_workers)
        task_count = sum(len(tasks) for tasks in registered_tasks.values())
        
        # Guardar métricas
        cache.set('celery:worker_count', worker_count, timeout=300)
        cache.set('celery:task_count', task_count, timeout=300)
        
        return {
            'status': 'healthy' if worker_count > 0 else 'warning',
            'workers': worker_count,
            'registered_tasks': task_count,
            'active_tasks': len(active_workers.get(list(active_workers.keys())[0], [])) if active_workers else 0,
        }
        
    except Exception as e:
        logger.error(f"Failed to check workers: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(queue='monitoring')
def monitor_queue_sizes():
    """Monitorea el tamaño de las colas (aproximado)"""
    try:
        import redis
        
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            return {'error': 'REDIS_URL not configured'}
        
        r = redis.from_url(redis_url)
        
        # Nota: Esta es una aproximación, Redis no tiene colas nativas
        # Celery usa listas para cada cola
        queues = ['celery', 'uploads', 'maintenance', 'monitoring']
        queue_sizes = {}
        
        for queue in queues:
            # Celery usa el patrón: {queue_name} para mensajes pendientes
            pending_key = f'celery@{queue}'
            try:
                # Esto varía según la versión de Celery
                size = r.llen(pending_key) if r.exists(pending_key) else 0
                queue_sizes[queue] = size
            except:
                queue_sizes[queue] = 0
        
        # Guardar en cache
        cache.set('celery:queue_sizes', queue_sizes, timeout=300)
        
        # Alertar si alguna cola tiene demasiados mensajes
        alerts = []
        for queue, size in queue_sizes.items():
            if size > 100:  # Límite configurable
                alerts.append(f"Queue '{queue}' has {size} pending tasks")
        
        return {
            'queues': queue_sizes,
            'total_pending': sum(queue_sizes.values()),
            'alerts': alerts,
            'timestamp': timezone.now().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Failed to monitor queues: {str(e)}")
        return {'error': str(e)}