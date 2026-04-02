# notifications/models.py
"""
Modelos para el sistema de notificaciones.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid


class Notification(models.Model):
    """
    Notificación para un usuario.
    """
    NOTIFICATION_TYPES = [
        ('purchase', 'Compra de canción'),
        ('hold_released', 'Hold liberado'),
        ('new_comment', 'Nuevo comentario'),
        ('low_balance', 'Saldo bajo'),
        ('system', 'Notificación del sistema'),
    ]
    
    CHANNELS = [
        ('email', 'Email'),
        ('push', 'Push notification'),
        ('in_app', 'In-app'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Usuario'
    )
    
    type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        verbose_name='Tipo',
        db_index=True
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Título'
    )
    
    message = models.TextField(
        verbose_name='Mensaje'
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadatos',
        help_text='Información adicional: song_id, amount, click_action, etc.'
    )
    
    channels = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Canales enviados',
        help_text='Registro de qué canales se enviaron'
    )
    
    read = models.BooleanField(
        default=False,
        verbose_name='Leído',
        db_index=True
    )
    
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Leído el'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Creado',
        db_index=True
    )
    
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Enviado'
    )
    
    class Meta:
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'read']),
            models.Index(fields=['type', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.title[:50]}"
    
    def mark_as_read(self):
        """Marcar notificación como leída"""
        if not self.read:
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])
    
    def mark_as_sent(self):
        """Marcar notificación como enviada"""
        self.sent_at = timezone.now()
        self.save(update_fields=['sent_at'])


class NotificationPreference(models.Model):
    """
    Preferencias de notificaciones por usuario.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name='Usuario'
    )
    
    # Preferencias por tipo y canal
    preferences = models.JSONField(
        default=dict,
        verbose_name='Preferencias',
        help_text='Estructura: {"push": {"purchase": true, ...}, "email": {...}}'
    )
    
    # Preferencias globales
    email_enabled = models.BooleanField(
        default=False,
        verbose_name='Email habilitado',
        help_text='Requiere configuración de SMTP'
    )
    
    push_enabled = models.BooleanField(
        default=True,
        verbose_name='Push habilitado'
    )
    
    in_app_enabled = models.BooleanField(
        default=True,
        verbose_name='In-app habilitado'
    )
    
    # Silencio nocturno (no enviar push en ciertas horas)
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Inicio silencio nocturno'
    )
    
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Fin silencio nocturno'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Creado'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Actualizado'
    )
    
    class Meta:
        verbose_name = 'Preferencia de notificación'
        verbose_name_plural = 'Preferencias de notificaciones'
    
    def __str__(self):
        return f"Preferencias de {self.user.email}"
    
    def get_preference(self, channel, notification_type):
        """Obtener preferencia para un canal y tipo específico."""
        channel_prefs = self.preferences.get(channel, {})
        return channel_prefs.get(notification_type, True)
    
    def set_preference(self, channel, notification_type, value):
        """Establecer preferencia para un canal y tipo."""
        if channel not in self.preferences:
            self.preferences[channel] = {}
        self.preferences[channel][notification_type] = value
        self.save(update_fields=['preferences', 'updated_at'])
    
    def should_send(self, channel, notification_type):
        """Determinar si se debe enviar una notificación."""
        # Verificar canal habilitado globalmente
        if channel == 'email' and not self.email_enabled:
            return False
        if channel == 'push' and not self.push_enabled:
            return False
        if channel == 'in_app' and not self.in_app_enabled:
            return False
        
        # Verificar preferencia específica
        return self.get_preference(channel, notification_type)
    
    def is_quiet_hours(self):
        """Verificar si estamos en horas de silencio."""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        now = timezone.now().time()
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end


class PushDevice(models.Model):
    """
    Dispositivos registrados para notificaciones push.
    """
    DEVICE_TYPES = [
        ('web', 'Web Push'),
        ('ios', 'iOS'),
        ('android', 'Android'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_devices',
        verbose_name='Usuario'
    )
    
    device_type = models.CharField(
        max_length=20,
        choices=DEVICE_TYPES,
        verbose_name='Tipo de dispositivo'
    )
    
    token = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Token de dispositivo',
        db_index=True
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    
    user_agent = models.TextField(
        blank=True,
        verbose_name='User Agent'
    )
    
    # Metadata para almacenar información específica del dispositivo
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadatos',
        help_text='Información adicional: subscription_info para web push, etc.'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Creado'
    )
    
    last_used = models.DateTimeField(
        auto_now=True,
        verbose_name='Último uso'
    )
    
    class Meta:
        verbose_name = 'Dispositivo push'
        verbose_name_plural = 'Dispositivos push'
        unique_together = [['user', 'token']]
    
    def __str__(self):
        return f"{self.user.email} - {self.device_type}"
    
    def clean(self):
        """Validar formato de token según dispositivo"""
        if self.device_type == 'web' and not self.token.startswith('web_'):
            raise ValidationError('Token web debe comenzar con "web_"')
        if self.device_type == 'ios' and len(self.token) != 64:
            raise ValidationError('Token iOS debe tener 64 caracteres')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)