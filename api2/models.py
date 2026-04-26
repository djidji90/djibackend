# api2/models.py
"""
Modelos de música para Eco-Music Platform
"""
from django.db import models
from django.core.validators import ValidationError
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import os
import uuid


# ============================================
# CONSTANTES DE PRECIOS (definidos por plataforma)
# ============================================
SONG_CATEGORIES = [
    ('standard', 'Estándar'),
    ('hit', 'Éxito/Sencillo popular'),
    ('premium', 'Premium'),
    ('classic', 'Clásico'),
]

SONG_PRICES = {
    'standard': Decimal('100.00'),   # 500 XAF
    'hit': Decimal('100.00'),        # 750 XAF
    'premium': Decimal('250.00'),   # 1000 XAF
    'classic': Decimal('250.00'),    # 300 XAF
}

# ============================================
# MODELO PRINCIPAL: SONG
# ============================================

class Song(models.Model):
    """
    Modelo de canción.
    Cualquier usuario puede subir canciones y recibir el 80% de las ventas.
    Los precios son definidos por la plataforma según categoría.
    """
    
    # --- INFORMACIÓN BÁSICA ---
    title = models.CharField(
        max_length=255,
        verbose_name='Título'
    )
    artist = models.CharField(
        max_length=255,
        verbose_name='Artista',
        help_text='Nombre artístico que se mostrará'
    )
    file_size = models.IntegerField(
        blank=True, 
        null=True,
        verbose_name='Tamaño del archivo'
    )
    file_format = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        verbose_name='Formato'
    )
    audio_file = models.FileField(
        upload_to='songs/audio/', 
        blank=True, 
        null=True,
        verbose_name='Archivo de audio'
    )
    cover_image = models.ImageField(
        upload_to='songs/covers/', 
        blank=True, 
        null=True,
        verbose_name='Imagen de portada'
    )
    genre = models.CharField(
        max_length=100,
        verbose_name='Género'
    )
    duration = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        verbose_name='Duración'
    )
    
    # --- ARCHIVOS EN R2 (Cloudflare) ---
    file_key = models.CharField(
        max_length=500, 
        unique=True, 
        default="songs/temp_file",
        verbose_name='Clave R2 (audio)'
    )
    image_key = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        verbose_name='Clave R2 (imagen)'
    )
    
    # --- MONETIZACIÓN (NUEVO) ---
    category = models.CharField(
        max_length=20,
        choices=SONG_CATEGORIES,
        default='standard',
        verbose_name='Categoría',
        help_text='Define el precio de la canción (según acuerdo plataforma-gremio)',
        db_index=True
    )
    
    is_purchasable = models.BooleanField(
        default=True,
        verbose_name='Disponible para compra',
        help_text='Si está activo, los usuarios pueden comprar esta canción'
    )
    
    # --- ESTADÍSTICAS DE VENTAS (NUEVO) ---
    sales_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name='Veces comprada'
    )
    
    total_revenue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False,
        verbose_name='Ingresos totales'
    )
    
    last_purchased_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='Última compra'
    )
    
    # --- ESTADÍSTICAS DE INTERACCIÓN ---
    likes_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Me gusta'
    )
    plays_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Reproducciones'
    )
    downloads_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Descargas'
    )
    
    # --- CONTROL DE ACCESO ---
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_songs',
        verbose_name='Subido por',
        help_text='Usuario que subió la canción (recibe el 80% de las ventas)'
    )
    is_public = models.BooleanField(
        default=True,
        verbose_name='Pública',
        help_text='Si es privada, solo el artista puede verla'
    )
    
    # --- TIMESTAMPS ---
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['artist']),
            models.Index(fields=['genre']),
            models.Index(fields=['created_at']),
            models.Index(fields=['category', 'is_purchasable']),
            models.Index(fields=['uploaded_by']),
        ]
        verbose_name = 'Canción'
        verbose_name_plural = 'Canciones'

    def __str__(self):
        return f"{self.title} by {self.artist}"

    # --- PROPIEDADES DE PRECIO ---
    @property
    def price(self):
        """Precio según categoría (definido por plataforma)"""
        return SONG_PRICES.get(self.category, SONG_PRICES['standard'])
    
    @property
    def artist_share(self):
        """80% para el artista que subió la canción"""
        return (self.price * Decimal('0.80')).quantize(Decimal('0.01'))
    
    @property
    def platform_share(self):
        """20% para la plataforma"""
        return self.price - self.artist_share
    
    @property
    def beneficiary(self):
        """Quién recibe el dinero (el que subió)"""
        return self.uploaded_by
    
    @property
    def can_be_purchased(self):
        """Verificar si la canción se puede comprar"""
        return self.is_purchasable and self.is_public and self.uploaded_by is not None
    
    @property
    def formatted_price(self):
        """Precio formateado para mostrar"""
        return f"{self.price:,.0f} XAF"
    
    # --- MÉTODOS DE VENTA ---
    def record_purchase(self, user, amount):
        """
        Registrar una compra (llamado por WalletService)
        """
        self.sales_count += 1
        self.total_revenue += Decimal(str(amount))
        self.last_purchased_at = timezone.now()
        self.save(update_fields=['sales_count', 'total_revenue', 'last_purchased_at'])
    
    def get_purchase_stats(self):
        """Estadísticas de compra para el artista"""
        return {
            'sales_count': self.sales_count,
            'total_revenue': float(self.total_revenue),
            'last_purchased': self.last_purchased_at.isoformat() if self.last_purchased_at else None,
            'price_per_unit': float(self.price),
            'artist_earned': float(self.artist_share * self.sales_count),
        }
    
    # --- MÉTODOS DE R2 ---
    def save(self, *args, **kwargs):
        """Guardar canción generando keys de R2 si es necesario"""
        if not self.file_key or self.file_key == "songs/temp_file":
            self.file_key = self.generate_r2_key('songs')
        if not self.image_key:
            self.image_key = self.generate_r2_key('images')
        
        super().save(*args, **kwargs)

    def generate_r2_key(self, folder):
        """Genera una key única para R2"""
        ext = '.mp3' if folder == 'songs' else '.jpg'
        unique_id = uuid.uuid4().hex[:12]
        return f"{folder}/{unique_id}{ext}"

    def delete(self, *args, **kwargs):
        """Eliminar archivos de R2 antes de borrar el objeto"""
        from .r2_utils import delete_file_from_r2
        
        if self.file_key and self.file_key != "songs/temp_file":
            delete_file_from_r2(self.file_key)
        if self.image_key:
            delete_file_from_r2(self.image_key)
            
        super().delete(*args, **kwargs)

    @property
    def file_name(self):
        """Nombre del archivo sin la ruta"""
        return os.path.basename(self.file_key) if self.file_key else None

    @property
    def image_name(self):
        """Nombre de la imagen sin la ruta"""
        return os.path.basename(self.image_key) if self.image_key else None


# ============================================
# MODELOS DE INTERACCIÓN
# ============================================

class Like(models.Model):
    """Registro de me gusta en canciones"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    song = models.ForeignKey(
        Song, 
        on_delete=models.CASCADE, 
        related_name='likes',
        verbose_name='Canción'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha'
    )

    class Meta:
        unique_together = ('user', 'song')
        ordering = ['-created_at']
        verbose_name = 'Me gusta'
        verbose_name_plural = 'Me gusta'

    def __str__(self):
        return f"{self.user.username} likes {self.song.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.song.likes_count = Like.objects.filter(song=self.song).count()
        self.song.save(update_fields=['likes_count'])

    def delete(self, *args, **kwargs):
        song = self.song
        super().delete(*args, **kwargs)
        song.likes_count = Like.objects.filter(song=song).count()
        song.save(update_fields=['likes_count'])


class Download(models.Model):
    """Registro de descargas de canciones"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    song = models.ForeignKey(
        Song, 
        on_delete=models.CASCADE, 
        related_name='downloads',
        verbose_name='Canción'
    )
    downloaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha descarga'
    )
    ip_address = models.GenericIPAddressField(
        blank=True, 
        null=True,
        verbose_name='Dirección IP'
    )
    user_agent = models.TextField(
        blank=True, 
        null=True,
        verbose_name='User Agent'
    )
    download_token = models.CharField(
        max_length=64, 
        blank=True,
        verbose_name='Token de descarga'
    )
    is_confirmed = models.BooleanField(
        default=False,
        verbose_name='¿Confirmada?'
    )

    class Meta:
        ordering = ['-downloaded_at']
        indexes = [
            models.Index(fields=['downloaded_at']),
            models.Index(fields=['download_token']),
            models.Index(fields=['is_confirmed']),
        ]
        verbose_name = 'Descarga'
        verbose_name_plural = 'Descargas'

    def __str__(self):
        return f"{self.user.username} downloaded {self.song.title}"


class PlayHistory(models.Model):
    """Registro de reproducciones para analytics"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    song = models.ForeignKey(
        Song, 
        on_delete=models.CASCADE, 
        related_name='play_history',
        verbose_name='Canción'
    )
    played_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha reproducción'
    )
    duration_played = models.IntegerField(
        default=0,
        verbose_name='Segundos reproducidos'
    )
    ip_address = models.GenericIPAddressField(
        blank=True, 
        null=True,
        verbose_name='Dirección IP'
    )

    class Meta:
        ordering = ['-played_at']
        indexes = [
            models.Index(fields=['played_at']),
        ]
        verbose_name = 'Historial de reproducción'
        verbose_name_plural = 'Historial de reproducciones'

    def __str__(self):
        return f"{self.user.username} played {self.song.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.duration_played >= 30:
            self.song.plays_count += 1
            self.song.save(update_fields=['plays_count'])


class Comment(models.Model):
    """Comentarios en canciones"""
    song = models.ForeignKey(
        Song, 
        related_name="comments", 
        on_delete=models.CASCADE,
        verbose_name='Canción'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name="comments", 
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    content = models.TextField(
        max_length=1000,
        verbose_name='Contenido'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )
    is_edited = models.BooleanField(
        default=False,
        verbose_name='¿Editado?'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['song', '-created_at'], name='comment_song_created_idx'),
            models.Index(fields=['user', '-created_at'], name='comment_user_created_idx'),
            models.Index(fields=['-created_at'], name='comment_created_idx'),
        ]
        verbose_name = 'Comentario'
        verbose_name_plural = 'Comentarios'

    def __str__(self):
        return f"{self.user.username} - {self.song.title}"

    def clean(self):
        if len(self.content.strip()) == 0:
            raise ValidationError("El comentario no puede estar vacío.")
        if len(self.content.strip()) > 1000:
            raise ValidationError("El comentario no puede tener más de 1000 caracteres.")

    def save(self, *args, **kwargs):
        self.clean()
        
        if self.pk:
            try:
                original = Comment.objects.get(pk=self.pk)
                if original.content != self.content:
                    self.is_edited = True
            except Comment.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)


class CommentReaction(models.Model):
    """Reacciones a comentarios (like, love, laugh, etc.)"""
    REACTION_TYPES = [
        ('like', 'Like'),
        ('love', 'Love'),
        ('laugh', 'Laugh'),
        ('sad', 'Sad'),
        ('angry', 'Angry'),
    ]
    
    comment = models.ForeignKey(
        Comment, 
        related_name="reactions", 
        on_delete=models.CASCADE,
        verbose_name='Comentario'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        related_name="reactions", 
        on_delete=models.CASCADE,
        verbose_name='Usuario'
    )
    reaction_type = models.CharField(
        max_length=10, 
        choices=REACTION_TYPES, 
        default='like',
        verbose_name='Tipo de reacción'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha'
    )

    class Meta:
        unique_together = ('comment', 'user')
        ordering = ['-created_at']
        verbose_name = 'Reacción'
        verbose_name_plural = 'Reacciones'

    def __str__(self):
        return f"{self.user.username} {self.reaction_type}d {self.comment}"


# ============================================
# MODELO DE EVENTOS
# ============================================

class MusicEvent(models.Model):
    """Eventos musicales (conciertos, festivales, etc.)"""
    EVENT_TYPES = [
        ('concert', 'Concierto'),
        ('festival', 'Festival'),
        ('party', 'Fiesta'),
        ('workshop', 'Taller'),
        ('other', 'Otro'),
    ]
    
    title = models.CharField(
        max_length=255,
        verbose_name='Título'
    )
    description = models.TextField(
        verbose_name='Descripción'
    )
    event_type = models.CharField(
        max_length=20, 
        choices=EVENT_TYPES, 
        default='concert',
        verbose_name='Tipo de evento'
    )
    event_date = models.DateTimeField(
        verbose_name='Fecha del evento'
    )
    location = models.CharField(
        max_length=255,
        verbose_name='Ubicación'
    )
    venue = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name='Lugar específico'
    )
    image_key = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        verbose_name='Clave R2 (imagen)'
    )
    ticket_url = models.URLField(
        blank=True, 
        null=True,
        verbose_name='URL de entradas'
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name='Precio'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    is_featured = models.BooleanField(
        default=False,
        verbose_name='Destacado'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        ordering = ['-event_date']
        indexes = [
            models.Index(fields=['event_date']),
            models.Index(fields=['is_active']),
        ]
        verbose_name = 'Evento musical'
        verbose_name_plural = 'Eventos musicales'

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        if self.image_key:
            from .r2_utils import delete_file_from_r2
            delete_file_from_r2(self.image_key)
        super().delete(*args, **kwargs)

    @property
    def is_upcoming(self):
        return self.event_date > timezone.now()

    @property
    def days_until_event(self):
        if self.event_date:
            delta = self.event_date - timezone.now()
            return max(0, delta.days)
        return None


# ============================================
# MODELO DE PERFIL DE USUARIO
# ============================================

class UserProfile(models.Model):
    """Perfil extendido de usuario"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='profile',
        verbose_name='Usuario'
    )
    bio = models.TextField(
        max_length=500, 
        blank=True, 
        null=True,
        verbose_name='Biografía'
    )
    avatar_key = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        verbose_name='Clave R2 (avatar)'
    )
    website = models.URLField(
        blank=True, 
        null=True,
        verbose_name='Sitio web'
    )
    location = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='Ubicación'
    )
    favorite_genres = models.JSONField(
        default=list, 
        blank=True,
        verbose_name='Géneros favoritos'
    )
    notifications_enabled = models.BooleanField(
        default=True,
        verbose_name='Notificaciones activadas'
    )
    songs_uploaded = models.PositiveIntegerField(
        default=0,
        verbose_name='Canciones subidas'
    )
    total_listening_time = models.PositiveIntegerField(
        default=0,
        verbose_name='Tiempo total escuchado (segundos)'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        verbose_name = 'Perfil de usuario'
        verbose_name_plural = 'Perfiles de usuario'

    def __str__(self):
        return f"Profile of {self.user.username}"

    def delete(self, *args, **kwargs):
        if self.avatar_key:
            from .r2_utils import delete_file_from_r2
            delete_file_from_r2(self.avatar_key)
        super().delete(*args, **kwargs)


# ============================================
# MODELOS DE UPLOAD (R2)
# ============================================

class UploadSession(models.Model):
    """Sesión de upload directo a R2 con confirmación manual"""
    
    UPLOAD_STATUS_CHOICES = [
        ('pending', 'Pendiente - URL generada'),
        ('uploaded', 'Subido a R2 - Esperando confirmación'),
        ('confirmed', 'Confirmado - En procesamiento'),
        ('processing', 'Procesando en background'),
        ('ready', 'Completado - Canción lista'),
        ('failed', 'Fallido'),
        ('expired', 'Expirado'),
        ('cancelled', 'Cancelado'),
    ]
    
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upload_sessions',
        verbose_name='Usuario'
    )
    file_name = models.CharField(
        max_length=255,
        verbose_name='Nombre del archivo'
    )
    file_size = models.BigIntegerField(
        verbose_name='Tamaño del archivo'
    )
    file_type = models.CharField(
        max_length=100, 
        blank=True, 
        default='',
        verbose_name='Tipo MIME'
    )
    original_file_name = models.CharField(
        max_length=255,
        verbose_name='Nombre original'
    )
    file_key = models.CharField(
        max_length=500,
        verbose_name='Clave R2'
    )
    image_key = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        verbose_name='Clave R2 (imagen)'
    )
    status = models.CharField(
        max_length=20, 
        choices=UPLOAD_STATUS_CHOICES, 
        default='pending',
        verbose_name='Estado'
    )
    status_message = models.TextField(
        blank=True, 
        null=True,
        verbose_name='Mensaje de estado'
    )
    confirmed = models.BooleanField(
        default=False,
        verbose_name='Confirmado'
    )
    confirmed_at = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name='Fecha confirmación'
    )
    expires_at = models.DateTimeField(
        verbose_name='Fecha expiración'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name='Fecha completado'
    )
    song = models.ForeignKey(
        'Song',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_sessions',
        verbose_name='Canción creada'
    )
    metadata = models.JSONField(
        default=dict, 
        blank=True,
        verbose_name='Metadatos'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['confirmed']),
        ]
        verbose_name = 'Sesión de subida'
        verbose_name_plural = 'Sesiones de subida'

    def __str__(self):
        return f"Upload {self.id} - {self.user.username} - {self.status}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def can_upload(self):
        return self.status in ['pending', 'uploaded'] and not self.is_expired

    @property
    def can_confirm(self):
        return (
            self.status in ['pending', 'uploaded'] and
            not self.is_expired and 
            not self.confirmed and
            not self.completed_at
        )

    def mark_as_uploaded(self):
        self.status = 'uploaded'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_confirmed(self):
        self.status = 'confirmed'
        self.confirmed = True
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'confirmed', 'confirmed_at', 'updated_at'])

    def mark_as_processing(self):
        self.status = 'processing'
        self.save(update_fields=['status', 'updated_at'])

    def mark_as_ready(self, song):
        self.status = 'ready'
        self.song = song
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'song', 'completed_at', 'updated_at'])

    def mark_as_failed(self, error_message):
        self.status = 'failed'
        self.status_message = error_message[:500]
        self.save(update_fields=['status', 'status_message', 'updated_at'])

    def mark_as_expired(self):
        self.status = 'expired'
        self.save(update_fields=['status', 'updated_at'])


class UploadQuota(models.Model):
    """Límites de upload por usuario"""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='upload_quota',
        verbose_name='Usuario'
    )
    daily_uploads_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Subidas diarias'
    )
    daily_uploads_size = models.BigIntegerField(
        default=0,
        verbose_name='Tamaño subido hoy'
    )
    daily_uploads_reset_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='Reset diario'
    )
    pending_uploads_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Subidas pendientes'
    )
    pending_uploads_size = models.BigIntegerField(
        default=0,
        verbose_name='Tamaño pendiente'
    )
    total_uploads_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Total subidas'
    )
    total_uploads_size = models.BigIntegerField(
        default=0,
        verbose_name='Total tamaño'
    )
    max_daily_uploads = models.PositiveIntegerField(
        default=50,
        verbose_name='Límite subidas diarias'
    )
    max_daily_size = models.BigIntegerField(
        default=500 * 1024 * 1024,
        verbose_name='Límite tamaño diario'
    )
    max_file_size = models.BigIntegerField(
        default=100 * 1024 * 1024,
        verbose_name='Tamaño máximo por archivo'
    )
    max_total_storage = models.BigIntegerField(
        default=5 * 1024 * 1024 * 1024,
        verbose_name='Almacenamiento total máximo'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        indexes = [
            models.Index(fields=['daily_uploads_reset_at']),
        ]
        verbose_name = 'Cuota de subida'
        verbose_name_plural = 'Cuotas de subida'

    def reset_if_needed(self):
        if timezone.now() > self.daily_uploads_reset_at + timezone.timedelta(days=1):
            self.daily_uploads_count = 0
            self.daily_uploads_size = 0
            self.daily_uploads_reset_at = timezone.now()
            self.save()

    def can_upload(self, file_size, check_pending=True):
        self.reset_if_needed()
        
        if file_size > self.max_file_size:
            return False, f"Archivo demasiado grande. Máximo: {self.max_file_size // (1024*1024)}MB"
        
        if self.total_uploads_size + file_size > self.max_total_storage:
            available_mb = (self.max_total_storage - self.total_uploads_size) // (1024 * 1024)
            return False, f"Límite de almacenamiento alcanzado. Disponible: {available_mb}MB"
        
        if self.daily_uploads_count >= self.max_daily_uploads:
            return False, "Límite diario de uploads alcanzado"
        
        if self.daily_uploads_size + file_size > self.max_daily_size:
            available_mb = (self.max_daily_size - self.daily_uploads_size) // (1024 * 1024)
            return False, f"Límite diario de tamaño alcanzado. Disponible: {available_mb}MB"
        
        if check_pending:
            pending_with_new = self.pending_uploads_size + file_size
            max_pending = self.max_daily_size * 2
            if pending_with_new > max_pending:
                return False, "Demasiados uploads en proceso. Espera a que se completen algunos."
        
        return True, None

    def reserve_quota(self, file_size):
        self.pending_uploads_count += 1
        self.pending_uploads_size += file_size
        self.save()

    def release_pending_quota(self, file_size):
        self.pending_uploads_count = max(0, self.pending_uploads_count - 1)
        self.pending_uploads_size = max(0, self.pending_uploads_size - file_size)
        self.save()

    def confirm_upload(self, file_size):
        self.pending_uploads_count = max(0, self.pending_uploads_count - 1)
        self.pending_uploads_size = max(0, self.pending_uploads_size - file_size)
        self.daily_uploads_count += 1
        self.daily_uploads_size += file_size
        self.total_uploads_count += 1
        self.total_uploads_size += file_size
        self.save()

    def get_quota_info(self):
        self.reset_if_needed()
        
        return {
            'daily': {
                'uploads': {
                    'used': self.daily_uploads_count,
                    'max': self.max_daily_uploads,
                    'remaining': self.max_daily_uploads - self.daily_uploads_count
                },
                'size': {
                    'used_bytes': self.daily_uploads_size,
                    'used_mb': round(self.daily_uploads_size / (1024 * 1024), 2),
                    'max_bytes': self.max_daily_size,
                    'max_mb': self.max_daily_size // (1024 * 1024),
                    'remaining_bytes': self.max_daily_size - self.daily_uploads_size,
                    'remaining_mb': (self.max_daily_size - self.daily_uploads_size) // (1024 * 1024)
                }
            },
            'pending': {
                'count': self.pending_uploads_count,
                'size_bytes': self.pending_uploads_size,
                'size_mb': round(self.pending_uploads_size / (1024 * 1024), 2)
            },
            'limits': {
                'file_size_mb': self.max_file_size // (1024 * 1024),
                'total_storage_gb': self.max_total_storage // (1024 * 1024 * 1024)
            },
            'totals': {
                'count': self.total_uploads_count,
                'size_gb': round(self.total_uploads_size / (1024 * 1024 * 1024), 2)
            },
            'reset_at': self.daily_uploads_reset_at.isoformat()
        }
        
# ============================================
# 📀 PLAYLISTS CURADAS POR LA PLATAFORMA
# ============================================

class CuratedPlaylist(models.Model):

    class PlaylistType(models.TextChoices):
        TEMPORAL     = 'temporal',     'Temporal (actualización frecuente)'
        GENERICA     = 'generica',     'Genérica (por género/estilo)'
        NICHO        = 'nicho',        'Nicho (específico, localizado)'
        MOOD         = 'mood',         'Por estado de ánimo'
        PROMOCIONAL  = 'promocional',  'Promocional / Patrocinada'

    class UpdateFrequency(models.TextChoices):
        HOURLY  = 'hourly',  'Cada hora'
        DAILY   = 'daily',   'Diaria'
        WEEKLY  = 'weekly',  'Semanal'
        MONTHLY = 'monthly', 'Mensual'
        NEVER   = 'never',   'Nunca (manual)'

    class AlgorithmType(models.TextChoices):
        MANUAL       = 'manual',       'Selección manual por staff'
        TRENDING     = 'trending',     'Tendencias (más populares)'
        NEW_RELEASES = 'new_releases', 'Nuevos lanzamientos'
        TOP_GENRE    = 'top_genre',    'Top por género'
        HYBRID       = 'hybrid',       'Híbrido (staff + algoritmo)'

    name          = models.CharField(max_length=200)
    slug          = models.SlugField(max_length=200, unique=True)
    description   = models.TextField(blank=True)
    cover_image   = models.CharField(max_length=500, blank=True)

    playlist_type      = models.CharField(max_length=20, choices=PlaylistType.choices, default=PlaylistType.GENERICA)
    update_frequency   = models.CharField(max_length=20, choices=UpdateFrequency.choices, default=UpdateFrequency.WEEKLY)
    algorithm          = models.CharField(max_length=20, choices=AlgorithmType.choices, default=AlgorithmType.MANUAL)

    min_songs      = models.PositiveIntegerField(default=10)
    max_songs      = models.PositiveIntegerField(default=50)
    target_genres  = models.JSONField(default=list, blank=True)
    target_country = models.CharField(max_length=5, blank=True)

    is_active  = models.BooleanField(default=True)
    priority   = models.IntegerField(default=0)
    featured   = models.BooleanField(default=False)

    last_calculated_at = models.DateTimeField(null=True, blank=True)
    song_count         = models.PositiveIntegerField(default=0)
    created_by         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_curated_playlists',
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    # Estadísticas cacheadas
    total_streams    = models.PositiveIntegerField(default=0)
    unique_listeners = models.PositiveIntegerField(default=0)
    saves_count      = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'playlist_type']),
            models.Index(fields=['slug']),
            models.Index(fields=['-priority']),
            models.Index(fields=['featured', 'is_active']),
        ]
        verbose_name = 'Playlist curada'
        verbose_name_plural = 'Playlists curadas'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while CuratedPlaylist.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_outdated(self):
        if self.update_frequency == self.UpdateFrequency.NEVER:
            return False
        if not self.last_calculated_at:
            return True
        from datetime import timedelta
        delta = timezone.now() - self.last_calculated_at
        freq_map = {
            self.UpdateFrequency.HOURLY:  timedelta(hours=1),
            self.UpdateFrequency.DAILY:   timedelta(days=1),
            self.UpdateFrequency.WEEKLY:  timedelta(days=7),
            self.UpdateFrequency.MONTHLY: timedelta(days=30),
        }
        return delta > freq_map.get(self.update_frequency, timedelta(days=7))

    def get_cover_url(self, request=None):
        if self.cover_image and self.cover_image.startswith('playlists/'):
            from .r2_utils import generate_presigned_url
            return generate_presigned_url(self.cover_image, expiration=3600)
        return self.cover_image or None


class CuratedPlaylistSong(models.Model):
    playlist  = models.ForeignKey(CuratedPlaylist, on_delete=models.CASCADE, related_name='songs_relation')
    song      = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='in_curated_playlists')
    position  = models.PositiveIntegerField(default=0)
    score     = models.FloatField(default=0.0)
    added_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='added_curated_songs',
    )
    added_at    = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['position']
        unique_together = [['playlist', 'song']]
        indexes = [
            models.Index(fields=['playlist', 'position']),
        ]

    def __str__(self):
        return f"{self.playlist.name} — {self.song.title} (#{self.position})"


class CuratedPlaylistSave(models.Model):
    playlist   = models.ForeignKey(CuratedPlaylist, on_delete=models.CASCADE, related_name='saves')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_curated_playlists')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['playlist', 'user']]
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.username} saved {self.playlist.name}"


class CuratedPlaylistAnalytics(models.Model):
    playlist              = models.ForeignKey(CuratedPlaylist, on_delete=models.CASCADE, related_name='analytics')
    date                  = models.DateField()
    total_streams         = models.PositiveIntegerField(default=0)
    unique_listeners      = models.PositiveIntegerField(default=0)
    avg_completion_rate   = models.FloatField(default=0.0)
    shares_count          = models.PositiveIntegerField(default=0)
    saves_count           = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [['playlist', 'date']]
        ordering = ['-date']
        indexes = [
            models.Index(fields=['playlist', 'date']),
        ]

    def __str__(self):
        return f"{self.playlist.name} — {self.date}"