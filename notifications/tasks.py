# notifications/tasks.py
"""
Tareas asíncronas para envío de notificaciones.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_notification_task(notification_id):
    """
    Tarea para enviar notificación de forma asíncrona.
    """
    from .models import Notification
    from .services import NotificationService
    
    try:
        notification = Notification.objects.get(id=notification_id)
        result = NotificationService.send_notification(notification)
        logger.info(f"Notificación {notification_id} enviada")
        return result
    except Notification.DoesNotExist:
        logger.error(f"Notificación {notification_id} no encontrada")
        return None
    except Exception as e:
        logger.error(f"Error enviando notificación {notification_id}: {e}")
        raise


@shared_task
def send_bulk_notifications(notification_ids):
    """
    Enviar múltiples notificaciones en lote.
    """
    results = []
    for nid in notification_ids:
        result = send_notification_task.delay(nid)
        results.append(result.id)
    return results