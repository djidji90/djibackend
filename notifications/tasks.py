# notifications/tasks.py
"""
Tareas asíncronas para envío de notificaciones.
"""
import logging
from celery import shared_task
from api2.models import CuratedPlaylist
from django.core.management import call_command

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

@shared_task(name='api2.tasks.update_curated_playlists')
def update_curated_playlists():
    """
    Actualiza playlists con frecuencia daily, weekly y monthly.
    Se ejecuta a las 3 AM diario.
    """
    from django.core.management import call_command
    try:
        call_command('update_playlists')
        logger.info("update_curated_playlists ejecutado correctamente")
        return "ok"
    except Exception as e:
        logger.error(f"Error en update_curated_playlists: {e}")
        raise


@shared_task(name='api2.tasks.update_curated_playlists_hourly')
def update_curated_playlists_hourly():
    """
    Actualiza solo las playlists con frecuencia hourly.
    Se ejecuta cada hora.
    """
   
    try:
        hourly_playlists = CuratedPlaylist.objects.filter(
            is_active=True,
            update_frequency='hourly',
            algorithm__in=['trending', 'new_releases', 'top_genre', 'hybrid']
        )
        for playlist in hourly_playlists:
            call_command('update_playlists', slug=playlist.slug, force=True)
            logger.info(f"Playlist horaria actualizada: {playlist.name}")
        return f"{hourly_playlists.count()} playlists horarias actualizadas"
    except Exception as e:
        logger.error(f"Error en update_curated_playlists_hourly: {e}")
        raise