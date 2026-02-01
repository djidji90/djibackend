# backend/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from kombu import Exchange, Queue
import logging

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

logger = logging.getLogger(__name__)

app = Celery('backend')

# Cargar configuración desde Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodescubrir tareas
app.autodiscover_tasks()

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
    
    # Logging mejorado
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',
)

# Manejo de señales para logging
@app.task(bind=True)
def debug_task(self):
    """Tarea de debug para verificar que Celery funciona"""
    logger.info(f'Celery debug task executed: {self.request.id}')
    return 'Celery is operational'

# Esta línea es CRÍTICA para Railway
if __name__ == '__main__':
    app.start()