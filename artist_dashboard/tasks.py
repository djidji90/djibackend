# artist_dashboard/tasks.py - CORREGIDO

import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from .services import DashboardService

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def update_all_artist_stats():
    """
    Actualizar estadísticas para todos los artistas.
    Ejecutar diariamente con celery beat.
    """
    artists = User.objects.filter(uploaded_songs__isnull=False).distinct()
    
    count = 0
    errors = 0
    for artist in artists:
        try:
            # ✅ CORREGIDO: Usar método público
            DashboardService.calculate_and_save(artist)
            count += 1
        except Exception as e:
            errors += 1
            logger.error(f"Error actualizando stats para {artist.id}: {e}")
    
    logger.info(f"Estadísticas actualizadas para {count} artistas, {errors} errores")
    return {'updated': count, 'errors': errors}


@shared_task
def update_artist_stats(artist_id):
    """
    Actualizar estadísticas para un artista específico.
    """
    try:
        artist = User.objects.get(id=artist_id)
        # ✅ CORREGIDO: Usar método público
        DashboardService.calculate_and_save(artist)
        logger.info(f"Estadísticas actualizadas para {artist.username}")
        return True
    except User.DoesNotExist:
        logger.error(f"Artista {artist_id} no encontrado")
        return False
    except Exception as e:
        logger.error(f"Error actualizando stats para {artist_id}: {e}")
        return False