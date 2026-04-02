# notifications/services.py
"""
Servicio central para envío de notificaciones.
PRIORIDAD: Push > In-app > Email (opcional)
"""

import logging
from django.conf import settings
from django.utils import timezone
from .models import Notification, NotificationPreference, PushDevice
from .push_providers import get_push_provider

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Servicio para crear y enviar notificaciones.
    """
    
    @staticmethod
    def create_notification(user, notification_type, title, message, metadata=None):
        """Crear una notificación en base de datos."""
        notification = Notification.objects.create(
            user=user,
            type=notification_type,
            title=title,
            message=message,
            metadata=metadata or {}
        )
        return notification
    
    @staticmethod
    def send_notification(notification, channels=None):
        """
        Enviar notificación por los canales especificados.
        Por defecto: push e in-app (email solo si se solicita explícitamente)
        """
        if channels is None:
            channels = ['push', 'in_app']
        
        try:
            prefs = notification.user.notification_preferences
        except NotificationPreference.DoesNotExist:
            prefs = None
        
        sent_channels = {}
        
        is_quiet = prefs and prefs.is_quiet_hours() if prefs else False
        critical_types = ['purchase', 'hold_released', 'low_balance']
        
        for channel in channels:
            if is_quiet and channel == 'push' and notification.type not in critical_types:
                logger.debug(f"Push omitido por horas de silencio: {notification.id}")
                sent_channels[channel] = 'quiet_hours'
                continue
            
            if prefs and not prefs.should_send(channel, notification.type):
                logger.debug(f"Notificación {notification.id} bloqueada por preferencias: {channel}")
                sent_channels[channel] = 'disabled_by_preferences'
                continue
            
            try:
                if channel == 'push':
                    sent = NotificationService._send_push(notification)
                elif channel == 'email':
                    sent = NotificationService._send_email(notification)
                elif channel == 'in_app':
                    sent = True
                else:
                    sent = False
                
                sent_channels[channel] = sent
                
            except Exception as e:
                logger.error(f"Error enviando notificación {notification.id} por {channel}: {e}")
                sent_channels[channel] = False
        
        notification.channels = sent_channels
        if any(v is True for v in sent_channels.values()):
            notification.mark_as_sent()
        else:
            notification.save(update_fields=['channels'])
        
        return sent_channels
    
    @staticmethod
    def _send_push(notification):
        """Enviar notificación push (PRIORIDAD ALTA)"""
        devices = PushDevice.objects.filter(
            user=notification.user,
            is_active=True
        )
        
        if not devices.exists():
            logger.debug(f"No hay dispositivos push para {notification.user.email}")
            return False
        
        success_count = 0
        
        for device in devices:
            provider = get_push_provider(device.device_type)
            
            if not provider:
                logger.warning(f"No hay proveedor para {device.device_type}")
                continue
            
            data = {
                'type': notification.type,
                'notification_id': str(notification.id),
                **notification.metadata
            }
            
            click_action = notification.metadata.get('click_action')
            
            if device.device_type in ['ios', 'android']:
                success = provider.send(
                    device_token=device.token,
                    title=notification.title,
                    body=notification.message,
                    data=data,
                    click_action=click_action
                )
            elif device.device_type == 'web':
                subscription_info = device.metadata.get('subscription_info', {})
                success = provider.send(
                    subscription_info=subscription_info,
                    title=notification.title,
                    body=notification.message,
                    data=data
                )
            else:
                success = False
            
            if success:
                success_count += 1
                device.last_used = timezone.now()
                device.save(update_fields=['last_used'])
        
        logger.info(f"Push enviado a {success_count}/{devices.count()} dispositivos")
        return success_count > 0
    
    @staticmethod
    def _send_email(notification):
        """Enviar notificación por email (OPCIONAL)"""
        if not getattr(settings, 'EMAIL_ENABLED', False):
            logger.debug("Email deshabilitado, omitiendo envío")
            return False
        
        if not settings.EMAIL_HOST_USER:
            logger.warning("EMAIL_HOST_USER no configurado")
            return False
        
        try:
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            from django.utils.html import strip_tags
            
            subject = notification.title
            html_message = render_to_string('notifications/email_template.html', {
                'notification': notification,
                'user': notification.user,
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            })
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
                html_message=html_message,
                fail_silently=False,
            )
            logger.info(f"Email enviado a {notification.user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Error enviando email: {e}")
            return False
    
    # ========== MÉTODOS DE NEGOCIO ==========
    
    @staticmethod
    def notify_purchase(artist, song, buyer, amount):
        """Notificar a artista sobre una compra"""
        title = "¡Alguien compró tu canción!"
        buyer_name = buyer.username if buyer else "Alguien"
        message = f"{buyer_name} compró '{song.title}' por {amount} XAF"
        metadata = {
            'song_id': song.id,
            'song_title': song.title,
            'buyer_id': buyer.id if buyer else None,
            'buyer_username': buyer_name,
            'amount': float(amount),
            'click_action': f'/artist/dashboard/song/{song.id}'
        }
        
        notification = NotificationService.create_notification(
            user=artist,
            notification_type='purchase',
            title=title,
            message=message,
            metadata=metadata
        )
        
        NotificationService.send_notification(notification, channels=['push', 'in_app'])
        return notification
    
    @staticmethod
    def notify_hold_released(artist, amount, song_title):
        """Notificar a artista sobre liberación de hold"""
        title = "¡Tus ganancias están disponibles!"
        message = f"{amount} XAF de '{song_title}' están disponibles para retirar"
        metadata = {
            'amount': float(amount),
            'song_title': song_title,
            'click_action': '/artist/dashboard/withdraw'
        }
        
        notification = NotificationService.create_notification(
            user=artist,
            notification_type='hold_released',
            title=title,
            message=message,
            metadata=metadata
        )
        
        NotificationService.send_notification(notification, channels=['push', 'in_app'])
        return notification
    
    @staticmethod
    def notify_new_comment(artist, song, commenter, comment_preview):
        """Notificar a artista sobre nuevo comentario"""
        title = f"Nuevo comentario en '{song.title}'"
        message = f"{commenter.username} comentó: \"{comment_preview[:100]}\""
        metadata = {
            'song_id': song.id,
            'song_title': song.title,
            'commenter_id': commenter.id,
            'commenter_username': commenter.username,
            'comment_preview': comment_preview[:100],
            'click_action': f'/song/{song.id}'
        }
        
        notification = NotificationService.create_notification(
            user=artist,
            notification_type='new_comment',
            title=title,
            message=message,
            metadata=metadata
        )
        
        NotificationService.send_notification(notification, channels=['push', 'in_app'])
        return notification
    
    @staticmethod
    def notify_low_balance(user, current_balance, min_balance=1000):
        """Notificar a usuario sobre saldo bajo"""
        title = "Tu saldo está bajo"
        message = f"Tu saldo actual es {current_balance} XAF. Recarga para seguir disfrutando."
        metadata = {
            'current_balance': float(current_balance),
            'min_balance': min_balance,
            'click_action': '/wallet/topup'
        }
        
        notification = NotificationService.create_notification(
            user=user,
            notification_type='low_balance',
            title=title,
            message=message,
            metadata=metadata
        )
        
        channels = ['push', 'in_app']
        if getattr(settings, 'EMAIL_ENABLED', False):
            channels.append('email')
        
        NotificationService.send_notification(notification, channels=channels)
        return notification