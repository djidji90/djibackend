from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
import logging
from datetime import timedelta

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

logger = logging.getLogger(__name__)

app = Celery('backend')

# Cargar configuración desde Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configuración específica para producción
app.conf.update(
    # Seguridad y estabilidad
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    
    # Para Railway/entornos cloud
    broker_connection_retry_on_startup=True,
    
    # Timeouts razonables para producción
    broker_connection_timeout=30,
    broker_connection_max_retries=3,
    
    # Prevenir pérdida de tareas
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    
    # ¡CRÍTICO! Timeouts para tareas (añadido)
    task_time_limit=30 * 60,  # 30 minutos máximos
    task_soft_time_limit=25 * 60,  # 25 minutos soft limit
    
    # Límites de workers (añadido)
    worker_max_tasks_per_child=50,
    worker_max_memory_per_child=300000,  # 300MB
    worker_prefetch_multiplier=1,
    worker_concurrency=2,  # Ajusta según RAM
    
    # Logging mejorado
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',
)

# Autodescubrir tareas
app.autodiscover_tasks()

# AÑADIR SEÑALES PARA MONITOREO (con imports correctos)
from celery.signals import worker_process_init, task_failure, task_success
import sys

@worker_process_init.connect
def init_worker(**kwargs):
    """Configura logging específico del worker"""
    logger.info(f"Worker {kwargs.get('worker_pid')} inicializado")
    # Log de configuración para debug
    logger.info(f"Time limits: soft={app.conf.task_soft_time_limit}s, hard={app.conf.task_time_limit}s")

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, **kw):
    """Log detallado de fallos de tarea"""
    logger.error(f"❌ Tarea falló - ID: {task_id}")
    logger.error(f"   Tarea: {sender.name}")
    logger.error(f"   Error: {exception}")
    logger.error(f"   Args: {args}")
    logger.error(f"   Kwargs: {kwargs}")

@task_success.connect
def handle_task_success(sender=None, result=None, task_id=None, **kwargs):
    """Log de éxito"""
    logger.info(f"✅ Tarea exitosa: {sender.name}, ID: {task_id}")
    if result:
        logger.info(f"   Resultado: {str(result)[:200]}")

# Tarea de debug
@app.task(bind=True)
def debug_task(self):
    """Tarea de debug para verificar que Celery funciona"""
    logger.info(f'🔧 Celery debug task executed: {self.request.id}')
    logger.info(f'   Worker: {self.request.hostname}')
    logger.info(f'   Queue: {self.request.delivery_info.get("routing_key", "unknown")}')
    return {
        'status': 'ok',
        'task_id': self.request.id,
        'worker': self.request.hostname
    }

# HEALTH CHECK CORREGIDO - Usando la forma correcta de importar inspect
@app.task(bind=True)
def health_check(self):
    """Health check completo del sistema Celery"""
    from django.utils import timezone
    
    try:
        # ✅ FORMA CORRECTA: usar current_app.control.inspect()
        inspect = app.control.inspect()
        
        # Verificar workers activos
        active_workers = inspect.ping() or {}
        workers_count = len(active_workers)
        
        # Verificar tareas activas
        active_tasks = inspect.active() or {}
        reserved_tasks = inspect.reserved() or {}
        
        # Estadísticas de workers
        stats = inspect.stats() or {}
        
        total_active = sum(len(tasks) for tasks in active_tasks.values())
        total_reserved = sum(len(tasks) for tasks in reserved_tasks.values())
        
        # Obtener versiones de Celery de los workers
        worker_versions = {}
        for worker_name, worker_stats in stats.items():
            if worker_stats:
                worker_versions[worker_name] = worker_stats.get('celery_version', 'unknown')
        
        result = {
            'status': 'healthy' if workers_count > 0 else 'degraded',
            'workers': {
                'count': workers_count,
                'names': list(active_workers.keys()),
                'versions': worker_versions
            },
            'tasks': {
                'active': total_active,
                'reserved': total_reserved,
                'total_pending': total_active + total_reserved
            },
            'timestamp': timezone.now().isoformat()
        }
        
        # Alertas si hay problemas
        if workers_count == 0:
            result['status'] = 'critical'
            result['alerts'] = ['No active workers found']
        elif total_reserved > 100:
            result['status'] = 'warning'
            result['alerts'] = [f'High task backlog: {total_reserved} reserved']
        
        logger.info(f"❤️ Health check: {result['status']} - {workers_count} workers, {total_active} active")
        return result
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}", exc_info=True)
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }

# Tarea para monitorear workers específicos
@app.task(bind=True)
def worker_stats(self):
    """Obtiene estadísticas detalladas de los workers"""
    try:
        inspect = app.control.inspect()
        
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}
        
        result = {}
        for worker_name in stats.keys():
            result[worker_name] = {
                'stats': stats.get(worker_name, {}),
                'active_count': len(active.get(worker_name, [])),
                'reserved_count': len(reserved.get(worker_name, [])),
                'scheduled_count': len(scheduled.get(worker_name, []))
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting worker stats: {e}")
        return {'error': str(e)}

# Esta línea es CRÍTICA para Railway
if __name__ == '__main__':
    app.start()