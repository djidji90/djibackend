# notifications/signals.py
"""
Señales para disparar notificaciones automáticamente.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging

from .services import NotificationService
from .models import NotificationPreference

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_notification_preferences(sender, instance, created, **kwargs):
    """Crear preferencias al crear usuario"""
    if created:
        NotificationPreference.objects.create(
            user=instance,
            email_enabled=False,
            push_enabled=True,
            in_app_enabled=True,
            preferences={
                'push': {
                    'purchase': True,
                    'hold_released': True,
                    'new_comment': True,
                    'low_balance': True,
                },
                'in_app': {
                    'purchase': True,
                    'hold_released': True,
                    'new_comment': True,
                    'low_balance': True,
                }
            }
        )
        logger.info(f"Preferencias de notificación creadas para {instance.email}")


@receiver(post_save, sender='wallet.Transaction')
def notify_on_purchase(sender, instance, created, **kwargs):
    """Notificar compra de canción"""
    if created and instance.transaction_type == 'purchase':
        try:
            metadata = instance.metadata or {}
            artist_id = metadata.get('artist_id')
            song_id = metadata.get('song_id')
            amount = abs(instance.amount)
            
            if artist_id and song_id:
                from django.contrib.auth import get_user_model
                from api2.models import Song
                
                User = get_user_model()
                artist = User.objects.filter(id=artist_id).first()
                song = Song.objects.filter(id=song_id).first()
                buyer = getattr(instance, 'created_by', None)
                
                if artist and song:
                    NotificationService.notify_purchase(
                        artist=artist,
                        song=song,
                        buyer=buyer,
                        amount=amount
                    )
        except Exception as e:
            logger.error(f"Error en notify_on_purchase: {e}")


@receiver(post_save, sender='wallet.Hold')
def notify_on_hold_release(sender, instance, **kwargs):
    """Notificar liberación de hold"""
    if instance.is_released and instance.released_at:
        try:
            transaction = instance.transaction
            metadata = transaction.metadata or {}
            song_title = metadata.get('song_title', 'tu canción')
            amount = instance.amount
            
            NotificationService.notify_hold_released(
                artist=instance.artist,
                amount=amount,
                song_title=song_title
            )
        except Exception as e:
            logger.error(f"Error en notify_on_hold_release: {e}")


@receiver(post_save, sender='api2.Comment')
def notify_on_new_comment(sender, instance, created, **kwargs):
    """Notificar nuevo comentario"""
    if created:
        try:
            song = instance.song
            artist = song.uploaded_by
            
            if artist and artist != instance.user:
                NotificationService.notify_new_comment(
                    artist=artist,
                    song=song,
                    commenter=instance.user,
                    comment_preview=instance.content[:100]
                )
        except Exception as e:
            logger.error(f"Error en notify_on_new_comment: {e}")