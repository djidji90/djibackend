from django.db import models
from django.core.validators import ValidationError
from django.conf import settings
import os
import uuid
from django.utils import timezone

class Song(models.Model):
    # Información básica
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    genre = models.CharField(max_length=100)
    duration = models.CharField(max_length=20, blank=True, null=True)
    
    # Archivos en R2
    file_key = models.CharField(max_length=500, unique=True, default="songs/temp_file")
    image_key = models.CharField(max_length=500, blank=True, null=True)
    
    # Metadata y estadísticas
    likes_count = models.PositiveIntegerField(default=0)
    plays_count = models.PositiveIntegerField(default=0)
    downloads_count = models.PositiveIntegerField(default=0)
    
    # Control de acceso y ownership
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_songs'
    )
    is_public = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['artist']),
            models.Index(fields=['genre']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.title} by {self.artist}"

    def save(self, *args, **kwargs):
        # ⚠️ CORRECCIÓN: Solo generar keys si no existen
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
        # Eliminar archivos de R2 antes de borrar el objeto
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


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'song')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} likes {self.song.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar contador de likes
        self.song.likes_count = Like.objects.filter(song=self.song).count()
        self.song.save(update_fields=['likes_count'])

    def delete(self, *args, **kwargs):
        song = self.song
        super().delete(*args, **kwargs)
        # Actualizar contador de likes
        song.likes_count = Like.objects.filter(song=song).count()
        song.save(update_fields=['likes_count'])


class Download(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='downloads')
    downloaded_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-downloaded_at']
        indexes = [
            models.Index(fields=['downloaded_at']),
        ]

    def __str__(self):
        return f"{self.user.username} downloaded {self.song.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar contador de descargas
        self.song.downloads_count = Download.objects.filter(song=self.song).count()
        self.song.save(update_fields=['downloads_count'])


class PlayHistory(models.Model):
    """Registro de reproducciones para analytics"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='play_history')
    played_at = models.DateTimeField(auto_now_add=True)
    duration_played = models.IntegerField(default=0)  # segundos reproducidos
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        ordering = ['-played_at']
        indexes = [
            models.Index(fields=['played_at']),
        ]

    def __str__(self):
        return f"{self.user.username} played {self.song.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar contador de reproducciones si se reprodujo más de 30 segundos
        if self.duration_played > 30:
            self.song.plays_count += 1
            self.song.save(update_fields=['plays_count'])


class Comment(models.Model):
    song = models.ForeignKey(Song, related_name="comments", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="comments", on_delete=models.CASCADE)
    content = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_edited = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.song.title}"

    def clean(self):
        if len(self.content.strip()) == 0:
            raise ValidationError("El comentario no puede estar vacío.")
        if len(self.content.strip()) > 1000:
            raise ValidationError("El comentario no puede tener más de 1000 caracteres.")

    def save(self, *args, **kwargs):
        # Marcar como editado si ya existe y está cambiando el contenido
        if self.pk:
            original = Comment.objects.get(pk=self.pk)
            if original.content != self.content:
                self.is_edited = True
        super().save(*args, **kwargs)


class CommentReaction(models.Model):
    REACTION_TYPES = [
        ('like', 'Like'),
        ('love', 'Love'),
        ('laugh', 'Laugh'),
        ('sad', 'Sad'),
        ('angry', 'Angry'),
    ]
    
    comment = models.ForeignKey(Comment, related_name="reactions", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reactions", on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=10, choices=REACTION_TYPES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} {self.reaction_type}d {self.comment}"


class MusicEvent(models.Model):
    EVENT_TYPES = [
        ('concert', 'Concierto'),
        ('festival', 'Festival'),
        ('party', 'Fiesta'),
        ('workshop', 'Taller'),
        ('other', 'Otro'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='concert')
    event_date = models.DateTimeField()
    location = models.CharField(max_length=255)
    venue = models.CharField(max_length=255, blank=True, null=True)
    
    # Imagen en R2
    image_key = models.CharField(max_length=500, blank=True, null=True)
    
    # Información de tickets
    ticket_url = models.URLField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Estado y visibilidad
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-event_date']
        indexes = [
            models.Index(fields=['event_date']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # ⚠️ CORRECCIÓN: Eliminada referencia a self.image que no existe
        # Solo generar key si no existe y se está subiendo una imagen
        # La lógica para asignar image_key debe manejarse en la vista/serializer
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Eliminar imagen de R2 antes de borrar el objeto
        if self.image_key:
            from .r2_utils import delete_file_from_r2
            delete_file_from_r2(self.image_key)
            
        super().delete(*args, **kwargs)

    @property
    def is_upcoming(self):
        """Verifica si el evento es futuro"""
        return self.event_date > timezone.now()

    @property
    def days_until_event(self):
        """Días hasta el evento"""
        if self.event_date:
            delta = self.event_date - timezone.now()
            return max(0, delta.days)
        return None


class UserProfile(models.Model):
    """Perfil extendido de usuario (opcional)"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, null=True)
    avatar_key = models.CharField(max_length=500, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    
    # Preferencias
    favorite_genres = models.JSONField(default=list, blank=True)  # ["rock", "pop", "jazz"]
    notifications_enabled = models.BooleanField(default=True)
    
    # Estadísticas
    songs_uploaded = models.PositiveIntegerField(default=0)
    total_listening_time = models.PositiveIntegerField(default=0)  # en segundos
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"

    def save(self, *args, **kwargs):
        # ⚠️ CORRECCIÓN: Eliminada referencia a self.avatar que no existe
        # La lógica para asignar avatar_key debe manejarse en la vista/serializer
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Eliminar avatar de R2 antes de borrar el objeto
        if self.avatar_key:
            from .r2_utils import delete_file_from_r2
            delete_file_from_r2(self.avatar_key)
            
        super().delete(*args, **kwargs)