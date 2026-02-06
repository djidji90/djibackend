from rest_framework import serializers
from .models import Song, Like, Download, Comment, CommentReaction, MusicEvent, PlayHistory, UserProfile
from .r2_utils import generate_presigned_url
from typing import List, Dict, Any, Optional
from django.contrib.auth import get_user_model
from .r2_utils import upload_file_to_r2, delete_file_from_r2, generate_presigned_url
import os
import uuid
from django.db import transaction
from django.utils import timezone

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'bio', 'avatar_url', 'website', 'location',
            'favorite_genres', 'songs_uploaded', 'total_listening_time',
            'created_at'
        ]
        read_only_fields = ['songs_uploaded', 'total_listening_time', 'created_at']

    def get_avatar_url(self, obj) -> Optional[str]:
        """Obtener URL firmada del avatar desde R2"""
        if obj.avatar_key:
            return generate_presigned_url(obj.avatar_key)
        return None


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 
            'full_name', 'profile', 'date_joined'
        ]
        read_only_fields = ['date_joined']

    def get_full_name(self, obj) -> str:
        """Nombre completo del usuario"""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class SongSerializer(serializers.ModelSerializer):
    # Campos del modelo
    file_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    # Campos calculados y relaciones
    likes_count = serializers.IntegerField(read_only=True)
    plays_count = serializers.IntegerField(read_only=True)
    downloads_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()
    
    # Información de ownership
    uploaded_by = UserSerializer(read_only=True)
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Song
        fields = [
            'id', 'title', 'artist', 'genre', 'duration',
            'file_url', 'image_url', 'file_key', 'image_key',
            'likes_count', 'plays_count', 'downloads_count', 
            'comments_count', 'comments',
            'uploaded_by', 'is_owner', 'is_public',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'file_key', 'image_key', 'likes_count', 'plays_count', 
            'downloads_count', 'uploaded_by', 'created_at', 'updated_at'
        ]

    def get_file_url(self, obj) -> Optional[str]:
        """Obtener URL firmada del archivo de audio desde R2"""
        if obj.file_key:
            return generate_presigned_url(obj.file_key)
        return None

    def get_image_url(self, obj) -> Optional[str]:
        """Obtener URL firmada de la imagen desde R2"""
        if obj.image_key:
            return generate_presigned_url(obj.image_key)
        return None

    def get_comments_count(self, obj) -> int:
        """Contar comentarios de la canción"""
        return obj.comments.count()

    def get_comments(self, obj) -> List[Dict[str, Any]]:
        """Obtener comentarios recientes"""
        comments = obj.comments.all()[:5]  # Últimos 5 comentarios
        return CommentSerializer(comments, many=True, context=self.context).data

    def get_is_owner(self, obj) -> bool:
        """Verificar si el usuario actual es el propietario"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.uploaded_by == request.user
        return False

    def validate_duration(self, value):
        """Validar formato de duración (MM:SS)"""
        if value and ':' in value:
            try:
                minutes, seconds = value.split(':')
                int(minutes)
                int(seconds)
            except (ValueError, TypeError):
                raise serializers.ValidationError("Formato de duración inválido. Use MM:SS")
        return value


class SongCreateSerializer(serializers.ModelSerializer):
    """Serializer específico para crear canciones"""
    class Meta:
        model = Song
        fields = [
            'title', 'artist', 'genre', 'duration', 'is_public'
        ]

    def create(self, validated_data):
        # El uploaded_by se asigna en la vista
        return super().create(validated_data)


class LikeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    song = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Like
        fields = ['id', 'user', 'song', 'created_at']
        read_only_fields = ['created_at']


class DownloadSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    song = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Download
        fields = ['id', 'user', 'song', 'downloaded_at', 'ip_address']
        read_only_fields = ['downloaded_at']


class PlayHistorySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    song = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = PlayHistory
        fields = ['id', 'user', 'song', 'played_at', 'duration_played', 'ip_address']
        read_only_fields = ['played_at']


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    song = serializers.StringRelatedField(read_only=True)
    is_user_comment = serializers.SerializerMethodField()
    reactions_count = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'song', 'user', 'content',
            'is_user_comment', 'reactions_count', 'user_reaction',
            'is_edited', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_edited', 'created_at', 'updated_at']

    def _get_current_user(self):
        """Helper para obtener usuario actual de forma segura"""
        request = self.context.get('request')
        if not request:
            return None
       
        user = getattr(request, 'user', None)
        if not user or not hasattr(user, 'is_authenticated'):
            return None
       
        return user if user.is_authenticated else None

    def get_is_user_comment(self, obj) -> bool:
        """Verificar si el comentario es del usuario actual"""
        user = self._get_current_user()
        return user is not None and obj.user == user

    def get_reactions_count(self, obj) -> Dict[str, int]:
        """Contar reacciones por tipo"""
        from django.db.models import Count
        try:
            reactions = obj.reactions.values('reaction_type').annotate(count=Count('id'))
            return {r['reaction_type']: r['count'] for r in reactions}
        except Exception:
            # En caso de error, retornar diccionario vacío
            return {}

    def get_user_reaction(self, obj) -> Optional[str]:
        """Obtener la reacción del usuario actual"""
        user = self._get_current_user()
        if not user:
            return None
       
        try:
            reaction = obj.reactions.get(user=user)
            return reaction.reaction_type
        except CommentReaction.DoesNotExist:
            return None
        except Exception:
            # Loggear error si es necesario
            # import logging
            # logger.error(f"Error obteniendo reacción: {e}", exc_info=True)
            return None

    def validate_content(self, value):
        """Validar contenido del comentario"""
        value = value.strip()
       
        if not value:
            raise serializers.ValidationError("El comentario no puede estar vacío.")
       
        if len(value) > 1000:
            raise serializers.ValidationError("El comentario no puede tener más de 1000 caracteres.")
       
        # Opcional: Validar contenido inapropiado
        # banned_words = ['spam', 'offensive']
        # for word in banned_words:
        #     if word in value.lower():
        #         raise serializers.ValidationError(f"El comentario contiene contenido no permitido.")
       
        return value

    def create(self, validated_data):
        """Sobrescribir create para añadir validaciones adicionales"""
        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
       
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Usuario no autenticado.")
       
        # Verificar límite de comentarios por usuario por día
        from django.utils import timezone
        from django.db.models import Count
       
        today = timezone.now().date()
        daily_comments = Comment.objects.filter(
            user=user,
            created_at__date=today
        ).count()
       
        if daily_comments >= 50:  # Límite de 50 comentarios por día
            raise serializers.ValidationError(
                "Has alcanzado el límite de comentarios por día (50)."
            )
       
        return super().create(validated_data)


class MusicEventSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    days_until_event = serializers.SerializerMethodField()
    is_upcoming = serializers.SerializerMethodField()

    class Meta:
        model = MusicEvent
        fields = [
            'id', 'title', 'description', 'event_type', 
            'event_date', 'location', 'venue',
            'image_url', 'ticket_url', 'price',
            'is_active', 'is_featured', 'is_upcoming', 'days_until_event',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_image_url(self, obj) -> Optional[str]:
        """Obtener URL firmada de la imagen del evento desde R2"""
        if obj.image_key:
            return generate_presigned_url(obj.image_key)
        return None

    def get_days_until_event(self, obj) -> Optional[int]:
        """Calcular días hasta el evento"""
        return obj.days_until_event

    def get_is_upcoming(self, obj) -> bool:
        """Verificar si el evento es futuro"""
        return obj.is_upcoming

    def validate_event_date(self, value):
        """Validar que la fecha del evento sea futura"""
        from django.utils import timezone
        if value and value < timezone.now():
            raise serializers.ValidationError("La fecha del evento debe ser futura")
        return value


class MusicEventCreateSerializer(serializers.ModelSerializer):
    """Serializer específico para crear eventos"""
    class Meta:
        model = MusicEvent
        fields = [
            'title', 'description', 'event_type', 'event_date',
            'location', 'venue', 'ticket_url', 'price',
            'is_active', 'is_featured'
        ]

# Agrega esto al final de tu api2/serializers.py

# api2/serializers.py - SOLO SongUploadSerializer (versión completa corregida)

class SongUploadSerializer(serializers.Serializer):
    """
    Serializador optimizado para subir canciones a R2 Cloudflare
    Versión corregida definitiva - Compatible con r2_client.py configurado
    """
    
    # Campos básicos de la canción
    title = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Título de la canción"
    )
    
    artist = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Artista o banda"
    )
    
    genre = serializers.CharField(
        max_length=100,
        required=True,
        help_text="Género musical (Rock, Pop, Jazz, etc.)"
    )
    
    duration = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default="",
        help_text="Duración en formato MM:SS (ej: 03:45)"
    )
    
    is_public = serializers.BooleanField(
        default=True,
        help_text="¿La canción es pública?"
    )
    
    # Campos de archivo
    audio_file = serializers.FileField(
        required=True,
        max_length=500,
        allow_empty_file=False,
        help_text="Archivo de audio (MP3, WAV, OGG, etc.) - Máx 100MB"
    )
    
    image_file = serializers.ImageField(
        required=False,
        allow_empty_file=True,
        max_length=500,
        help_text="Imagen de portada (JPG, PNG, WEBP) - Máx 10MB"
    )

    def validate_audio_file(self, value):
        """
        Validación optimizada para archivos de audio
        """
        # Validación 1: Tamaño máximo (100MB)
        MAX_SIZE = 100 * 1024 * 1024  # 100MB en bytes
        if value.size > MAX_SIZE:
            raise serializers.ValidationError(
                f"El archivo de audio es demasiado grande. "
                f"Máximo permitido: {MAX_SIZE / (1024*1024):.0f}MB"
            )
        
        # Validación 2: Extensión permitida
        valid_extensions = {
            '.mp3', '.wav', '.ogg', '.m4a', '.flac', 
            '.aac', '.webm', '.opus', '.mp4'
        }
        
        file_name = getattr(value, 'name', '')
        if not file_name:
            raise serializers.ValidationError("El archivo no tiene nombre")
        
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato de audio no soportado. "
                f"Formatos permitidos: {', '.join(sorted(valid_extensions))}"
            )
        
        # Validación 3: MIME type si está disponible
        content_type = getattr(value, 'content_type', '')
        if content_type:
            valid_mime_types = {
                'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/flac',
                'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/webm',
                'audio/opus', 'audio/x-m4a', 'audio/mp3'
            }
            
            if content_type not in valid_mime_types:
                # Verificar si es un MIME type genérico que podríamos aceptar
                if not content_type.startswith('audio/'):
                    raise serializers.ValidationError(
                        "El archivo no parece ser un archivo de audio válido"
                    )
        
        return value

    def validate_image_file(self, value):
        """
        Validación para archivos de imagen
        """
        if not value:
            return value  # Es opcional, así que None está bien
        
        # Validación 1: Tamaño máximo (10MB)
        MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
        if value.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError(
                f"La imagen es demasiado grande. "
                f"Máximo permitido: {MAX_IMAGE_SIZE / (1024*1024):.0f}MB"
            )
        
        # Validación 2: Extensión permitida
        valid_image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        
        file_name = getattr(value, 'name', '')
        file_ext = os.path.splitext(file_name)[1].lower()
        
        if file_ext not in valid_image_extensions:
            raise serializers.ValidationError(
                f"Formato de imagen no soportado. "
                f"Formatos permitidos: {', '.join(sorted(valid_image_extensions))}"
            )
        
        return value

    def validate_duration(self, value):
        """
        Validar formato de duración MM:SS
        """
        if not value or value.strip() == "":
            return ""  # Permitir vacío
        
        value = value.strip()
        
        # Validar formato básico
        if ':' not in value:
            raise serializers.ValidationError(
                "Formato de duración inválido. Use MM:SS (ej: 03:45)"
            )
        
        try:
            minutes_str, seconds_str = value.split(':')
            minutes = int(minutes_str)
            seconds = int(seconds_str)
            
            # Validar rangos razonables
            if minutes < 0 or minutes > 60:
                raise serializers.ValidationError(
                    "Los minutos deben estar entre 0 y 60"
                )
            
            if seconds < 0 or seconds >= 60:
                raise serializers.ValidationError(
                    "Los segundos deben estar entre 0 y 59"
                )
            
            # Validar duración mínima
            if minutes == 0 and seconds < 10:
                raise serializers.ValidationError(
                    "La duración mínima es 10 segundos"
                )
            
        except (ValueError, TypeError):
            raise serializers.ValidationError(
                "Formato de duración inválido. Use números (ej: 03:45)"
            )
        
        return value

    def validate(self, attrs):
        """
        Validación cruzada de campos
        """
        # Validar que el título no sea solo espacios
        title = attrs.get('title', '').strip()
        if not title:
            raise serializers.ValidationError({
                "title": "El título no puede estar vacío"
            })
        
        # Validar que el artista no sea solo espacios
        artist = attrs.get('artist', '').strip()
        if not artist:
            raise serializers.ValidationError({
                "artist": "El artista no puede estar vacío"
            })
        
        # Validar que el género no sea solo espacios
        genre = attrs.get('genre', '').strip()
        if not genre:
            raise serializers.ValidationError({
                "genre": "El género no puede estar vacío"
            })
        
        # Si se proporcionó imagen, asegurar que no sea un archivo de audio
        image_file = attrs.get('image_file')
        if image_file:
            image_name = getattr(image_file, 'name', '').lower()
            if any(image_name.endswith(ext) for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                raise serializers.ValidationError({
                    "image_file": "El archivo parece ser un audio, no una imagen"
                })
        
        return attrs

    def create(self, validated_data):
        """
        Creación atómica de canción con subida a R2
        VERSIÓN CORREGIDA DEFINITIVA - Compatible con tu r2_client.py
        """
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            raise serializers.ValidationError({
                "error": "No se pudo identificar al usuario"
            })
        
        user = request.user
        if not user.is_authenticated:
            raise serializers.ValidationError({
                "error": "Usuario no autenticado"
            })
        
        # Extraer datos
        title = validated_data['title'].strip()
        artist = validated_data['artist'].strip()
        genre = validated_data['genre'].strip()
        duration = validated_data.get('duration', '').strip()
        is_public = validated_data.get('is_public', True)
        audio_file = validated_data['audio_file']
        image_file = validated_data.get('image_file')
        
        # Generar keys únicas para R2
        import uuid
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"
        
        # Generar key para audio
        audio_ext = os.path.splitext(audio_file.name)[1].lower()
        audio_key = f"songs/audio/{unique_id}{audio_ext}"
        
        # Generar key para imagen (si existe)
        image_key = None
        if image_file:
            image_ext = os.path.splitext(image_file.name)[1].lower()
            image_key = f"songs/images/{unique_id}{image_ext}"
        
        # Iniciar transacción atómica
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # 1. Subir archivo de audio a R2
                audio_content_type = getattr(audio_file, 'content_type', None)
                if not upload_file_to_r2(audio_file, audio_key, content_type=audio_content_type):
                    raise serializers.ValidationError({
                        "audio_file": "No se pudo subir el archivo de audio a R2"
                    })
                
                # 2. Subir imagen a R2 (si existe)
                if image_file and image_key:
                    image_content_type = getattr(image_file, 'content_type', None)
                    if not upload_file_to_r2(image_file, image_key, content_type=image_content_type):
                        # Si falla la imagen, limpiar el audio ya subido
                        delete_file_from_r2(audio_key)
                        raise serializers.ValidationError({
                            "image_file": "No se pudo subir la imagen a R2"
                        })
                
                # 3. Crear registro en base de datos
                song = Song.objects.create(
                    title=title,
                    artist=artist,
                    genre=genre,
                    duration=duration,
                    is_public=is_public,
                    file_key=audio_key,
                    image_key=image_key,
                    uploaded_by=user,
                    # Campos adicionales útiles
                    file_size=audio_file.size,
                    file_format=audio_ext.lstrip('.'),
                )
                
                # 4. Actualizar estadísticas del usuario
                try:
                    profile, created = UserProfile.objects.get_or_create(
                        user=user,
                        defaults={'songs_uploaded': 1}
                    )
                    if not created:
                        profile.songs_uploaded += 1
                        profile.save(update_fields=['songs_uploaded'])
                except Exception as profile_error:
                    # No fallar la creación si hay error con el perfil
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error actualizando perfil de usuario: {profile_error}")
                
                # 5. Registrar log de creación
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Canción creada: ID={song.id}, "
                    f"Título='{title}', "
                    f"Artista='{artist}', "
                    f"Audio Key='{audio_key}', "
                    f"Usuario='{user.username}'"
                )
                
                return song
                
        except serializers.ValidationError:
            # Re-lanzar ValidationErrors para que DRF los maneje
            raise
            
        except Exception as e:
            # Manejo de errores inesperados
            
            # 6. LIMPIEZA EN CASO DE ERROR
            cleanup_errors = []
            
            # Intentar eliminar audio de R2
            try:
                if 'audio_key' in locals() and audio_key:
                    delete_file_from_r2(audio_key)
            except Exception as cleanup_error:
                cleanup_errors.append(f"Audio: {cleanup_error}")
            
            # Intentar eliminar imagen de R2
            try:
                if 'image_key' in locals() and image_key:
                    delete_file_from_r2(image_key)
            except Exception as cleanup_error:
                cleanup_errors.append(f"Imagen: {cleanup_error}")
            
            # Loggear error detallado
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(
                f"Error creando canción: {str(e)}\n"
                f"Traceback:\n{traceback.format_exc()}\n"
                f"Cleanup errors: {cleanup_errors}"
            )
            
            # Mensaje de error amigable
            error_message = str(e)
            if "timeout" in error_message.lower():
                error_message = "Timeout al subir archivos. Intenta de nuevo."
            elif "connection" in error_message.lower():
                error_message = "Error de conexión con el almacenamiento."
            else:
                error_message = "Error interno al procesar la solicitud."
            
            raise serializers.ValidationError({
                "error": error_message,
                "detail": "Por favor, intenta de nuevo. Si el problema persiste, contacta al administrador."
            })

    def to_representation(self, instance):
        """
        Personalizar respuesta después de crear la canción
        """
        from .serializers import SongSerializer
        
        # Usar SongSerializer para la respuesta
        song_serializer = SongSerializer(
            instance,
            context=self.context
        )
        
        # Añadir información adicional específica del upload
        representation = song_serializer.data
        representation.update({
            "upload_status": "success",
            "message": "Canción subida exitosamente",
            "audio_file_uploaded": bool(instance.file_key),
            "image_file_uploaded": bool(instance.image_key),
            "timestamp": instance.created_at.isoformat() if instance.created_at else None
        })
        
        return representation

# Serializadores básicos para respuestas simples
class SimpleMessageSerializer(serializers.Serializer):
    """Serializador para respuestas de mensajes simples"""
    message = serializers.CharField()
    status = serializers.CharField(required=False, allow_null=True)
    data = serializers.DictField(required=False, allow_null=True)

class LikesCountSerializer(serializers.Serializer):
    """Serializador para conteo de likes"""
    song_id = serializers.IntegerField()
    likes_count = serializers.IntegerField()
    title = serializers.CharField()

class ArtistListSerializer(serializers.Serializer):
    """Serializador para lista de artistas"""
    artists = serializers.ListField(child=serializers.CharField())

class SuggestionItemSerializer(serializers.Serializer):
    """Serializador para elementos de sugerencia"""
    id = serializers.IntegerField()
    title = serializers.CharField(allow_null=True)
    artist = serializers.CharField()
    genre = serializers.CharField()
    type = serializers.CharField()
    display = serializers.CharField()

class SuggestionsResponseSerializer(serializers.Serializer):
    """Serializador para respuesta de sugerencias"""
    suggestions = SuggestionItemSerializer(many=True)

class SearchSuggestionsSerializer(serializers.Serializer):
    """Serializador para sugerencias de búsqueda"""
    title = serializers.CharField()
    artist = serializers.CharField()
    genre = serializers.CharField()

class RandomSongsResponseSerializer(serializers.Serializer):
    """Serializador para respuesta de canciones aleatorias"""
    random_songs = SongSerializer(many=True)

class FileCheckSerializer(serializers.Serializer):
    """Serializador para verificación de archivos"""
    song_id = serializers.IntegerField()
    title = serializers.CharField()
    artist = serializers.CharField()
    files = serializers.DictField()

# Serializador para respuestas de APIView con archivos
class DownloadResponseSerializer(serializers.Serializer):
    """Serializador para respuesta de descarga (cuando hay error)"""
    error = serializers.CharField(required=False)
    message = serializers.CharField(required=False)
    retry_after = serializers.IntegerField(required=False)

class StreamResponseSerializer(serializers.Serializer):
    """Serializador para respuesta de streaming (cuando hay error)"""
    error = serializers.CharField(required=False)
    message = serializers.CharField(required=False)

# Serializador para métricas
class MetricsSerializer(serializers.Serializer):
    """Serializador para métricas del sistema"""
    timestamp = serializers.DateTimeField()
    general_stats = serializers.DictField()
    recent_activity = serializers.DictField()
    popular_content = serializers.DictField()

class UserMetricsSerializer(serializers.Serializer):
    """Serializador para métricas personales"""
    user_info = serializers.DictField()
    personal_stats = serializers.DictField()
    recent_activity_30d = serializers.DictField()

class HealthCheckSerializer(serializers.Serializer):
    """Serializador para health check"""
    status = serializers.CharField()
    timestamp = serializers.DateTimeField()
    service = serializers.CharField()
    version = serializers.CharField()

# api2/serializers/upload_direct.py
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
import os
import json

from datetime import datetime, timedelta
import re


class DirectUploadRequestSerializer(serializers.Serializer):
    """
    Serializer para solicitar upload directo a R2
    Valida y sanitiza datos del frontend
    """
    
    file_name = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Nombre del archivo con extensión (ej: 'mi-cancion.mp3')"
    )
    
    file_size = serializers.IntegerField(
        min_value=1,
        max_value=500 * 1024 * 1024,  # 500MB máximo absoluto
        required=True,
        help_text="Tamaño del archivo en bytes"
    )
    
    file_type = serializers.CharField(
        max_length=100,
        required=False,
        default="",
        allow_blank=True,
        help_text="Tipo MIME (ej: 'audio/mpeg', 'image/jpeg'). Si no se especifica, se detectará automáticamente."
    )
    
    metadata = serializers.DictField(
        required=False,
        default=dict,
        help_text="Metadatos adicionales del archivo"
    )
    
    class Meta:
        fields = ['file_name', 'file_size', 'file_type', 'metadata']
    
    def validate_file_name(self, value):
        """
        Validar nombre de archivo: seguridad y formato
        """
        if not value or not value.strip():
            raise ValidationError("El nombre del archivo no puede estar vacío")
        
        # Limpiar nombre
        cleaned_name = self._sanitize_filename(value)
        
        # Validar longitud después de limpieza
        if len(cleaned_name) > 200:
            raise ValidationError("El nombre del archivo es demasiado largo (máx. 200 caracteres)")
        
        # Validar que tenga extensión
        name_without_path = os.path.basename(cleaned_name)
        if '.' not in name_without_path:
            raise ValidationError("El archivo debe tener una extensión")
        
        # Obtener extensión
        _, ext = os.path.splitext(name_without_path)
        ext = ext.lower()
        
        # Extensiones permitidas
        allowed_extensions = {
            # Audio
            '.mp3', '.mpeg',
            '.wav', '.wave',
            '.ogg', '.oga',
            '.flac',
            '.m4a', '.mp4',
            '.aac',
            '.opus',
            '.wma',
            
            # Imágenes (para portadas)
            '.jpg', '.jpeg',
            '.png',
            '.webp',
            '.gif',
            '.bmp',
            '.svg',
            
            # Otros (metadata, letras, etc.)
            '.txt', '.json', '.xml',
            '.lrc',  # Lyrics
            '.pdf'
        }
        
        if ext not in allowed_extensions:
            raise ValidationError(
                f"Extensión '{ext}' no permitida. "
                f"Extensiones válidas: {', '.join(sorted(allowed_extensions))}"
            )
        
        # Validar nombres peligrosos
        dangerous_patterns = [
            r'\.\.',  # Directory traversal
            r'/', r'\\',  # Path separators
            r'^\s+', r'\s+$',  # Leading/trailing spaces
            r'[<>:"|?*]',  # Caracteres inválidos en Windows
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, name_without_path):
                raise ValidationError(
                    f"Nombre de archivo inválido: contiene caracteres no permitidos"
                )
        
        return cleaned_name
    
    def validate_file_size(self, value):
        """
        Validar tamaño del archivo con límites configurables
        """
        from django.conf import settings
        
        # Límite absoluto del sistema
        absolute_max = getattr(settings, 'MAX_UPLOAD_SIZE', 500 * 1024 * 1024)  # 500MB
        
        if value > absolute_max:
            mb = absolute_max // (1024 * 1024)
            raise ValidationError(
                f"El archivo es demasiado grande. Máximo permitido: {mb}MB"
            )
        
        # Validar que no sea 0 o negativo
        if value <= 0:
            raise ValidationError("El tamaño del archivo debe ser mayor a 0 bytes")
        
        # Validar tamaño mínimo (ej: 1KB para audio)
        min_size = 1024  # 1KB
        if value < min_size:
            raise ValidationError(
                f"El archivo es demasiado pequeño. Mínimo: {min_size} bytes"
            )
        
        return value
    
    def validate_file_type(self, value):
        """
        Validar/sanitizar tipo MIME
        """
        if not value:
            return ""
        
        # Tipos MIME permitidos
        allowed_mime_types = {
            # Audio
            'audio/mpeg', 'audio/mp3', 'audio/mp4',
            'audio/wav', 'audio/wave', 'audio/x-wav',
            'audio/ogg', 'audio/oga', 'application/ogg',
            'audio/flac', 'audio/x-flac',
            'audio/aac', 'audio/aacp',
            'audio/opus',
            'audio/x-ms-wma',
            'audio/webm',
            
            # Imágenes
            'image/jpeg', 'image/jpg',
            'image/png',
            'image/webp',
            'image/gif',
            'image/bmp',
            'image/svg+xml',
            
            # Otros
            'text/plain',
            'application/json',
            'application/xml', 'text/xml',
            'application/pdf',
            'application/octet-stream'  # Fallback genérico
        }
        
        # Limpiar y validar
        mime_type = value.strip().lower()
        
        # Si no está en la lista, intentar mapear por extensión
        if mime_type not in allowed_mime_types:
            # Podría ser un tipo válido pero con encoding diferente
            base_type = mime_type.split(';')[0].strip()
            if base_type in allowed_mime_types:
                return base_type
            
            # Si no se reconoce, usar vacío y detectar después
            return ""
        
        return mime_type
    
    def validate_metadata(self, value):
        """
        Validar metadatos adicionales
        """
        if not isinstance(value, dict):
            raise ValidationError("Los metadatos deben ser un objeto JSON")
        
        # Limitar tamaño de metadata (10KB máximo)
        metadata_json = json.dumps(value, separators=(',', ':'))
        if len(metadata_json) > 10 * 1024:  # 10KB
            raise ValidationError("Los metadatos son demasiado grandes (máx. 10KB)")
        
        # Validar/sanitizar campos específicos
        sanitized_metadata = {}
        
        # Campos permitidos en metadata
        allowed_fields = {
            'title', 'artist', 'album', 'genre', 'year',
            'track_number', 'disc_number', 'composer', 'lyricist',
            'is_public', 'license', 'language', 'mood', 'bpm',
            'original_name', 'custom_key', 'description', 'tags',
            'recording_date', 'location', 'instruments', 'duration',
            'bitrate', 'sample_rate', 'channels'
        }
        
        for key, val in value.items():
            # Sanitizar nombres de campos
            if key not in allowed_fields:
                # Campos personalizados deben tener prefijo 'custom_'
                if not key.startswith('custom_'):
                    continue  # Ignorar campos no permitidos
            
            # Sanitizar valores según tipo
            if isinstance(val, str):
                # Limitar longitud de strings
                sanitized_val = val[:500]  # Máximo 500 caracteres
            elif isinstance(val, (int, float)):
                sanitized_val = val
            elif isinstance(val, bool):
                sanitized_val = val
            elif isinstance(val, list):
                # Listas solo de strings, máximo 50 items
                sanitized_val = [
                    str(item)[:100] for item in val[:50] if isinstance(item, (str, int, float))
                ]
            elif isinstance(val, dict):
                # Sub-objetos limitados
                sanitized_val = {k: str(v)[:100] for k, v in list(val.items())[:10]}
            else:
                # Convertir otros tipos a string
                sanitized_val = str(val)[:200]
            
            sanitized_metadata[key] = sanitized_val
        
        return sanitized_metadata
    
    def validate(self, data):
        """
        Validación cruzada entre campos
        """
        # Verificar consistencia entre nombre de archivo y tipo MIME
        file_name = data.get('file_name', '')
        file_type = data.get('file_type', '')
        
        if file_name and not file_type:
            # Intentar detectar tipo MIME por extensión
            detected_type = self._detect_mime_from_extension(file_name)
            if detected_type:
                data['file_type'] = detected_type
        
        # Verificar que metadata no sobrescriba campos reservados
        metadata = data.get('metadata', {})
        reserved_fields = ['file_name', 'file_size', 'file_type', 'upload_id']
        for field in reserved_fields:
            if field in metadata:
                raise ValidationError(
                    f"El campo '{field}' está reservado y no puede usarse en metadata"
                )
        
        # Validar tamaño máximo basado en tipo de archivo
        file_size = data.get('file_size', 0)
        file_type = data.get('file_type', '')
        
        if file_type.startswith('audio/'):
            max_audio_size = 300 * 1024 * 1024  # 300MB para audio
            if file_size > max_audio_size:
                raise ValidationError(
                    f"Los archivos de audio no pueden exceder {max_audio_size // (1024*1024)}MB"
                )
        elif file_type.startswith('image/'):
            max_image_size = 50 * 1024 * 1024  # 50MB para imágenes
            if file_size > max_image_size:
                raise ValidationError(
                    f"Las imágenes no pueden exceder {max_image_size // (1024*1024)}MB"
                )
        
        return data
    
    # ==================== MÉTODOS HELPER ====================
    
    def _sanitize_filename(self, filename):
        """
        Sanitiza nombre de archivo para seguridad
        """
        # Remover path traversal attempts
        filename = os.path.basename(filename)
        
        # Remover caracteres peligrosos
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
        for char in dangerous_chars:
            filename = filename.replace(char, '_')
        
        # Remover múltiples espacios y puntos
        filename = re.sub(r'\s+', ' ', filename)
        filename = re.sub(r'\.\.+', '.', filename)
        
        # Trim y limitar longitud
        filename = filename.strip()
        
        return filename[:200]  # Limitar a 200 caracteres
    
    def _detect_mime_from_extension(self, filename):
        """
        Detecta tipo MIME basado en extensión de archivo
        """
        _, ext = os.path.splitext(filename.lower())
        
        mime_map = {
            # Audio
            '.mp3': 'audio/mpeg',
            '.mpeg': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.wave': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.oga': 'audio/ogg',
            '.flac': 'audio/flac',
            '.m4a': 'audio/mp4',
            '.mp4': 'audio/mp4',
            '.aac': 'audio/aac',
            '.opus': 'audio/opus',
            '.wma': 'audio/x-ms-wma',
            
            # Imágenes
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.svg': 'image/svg+xml',
            
            # Otros
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.lrc': 'text/plain',  # Lyrics
            '.pdf': 'application/pdf',
        }
        
        return mime_map.get(ext, '')


class UploadConfirmationSerializer(serializers.Serializer):
    """
    Serializer para confirmar que un archivo fue subido exitosamente
    """
    
    checksum = serializers.CharField(
        required=False,
        max_length=64,
        allow_blank=True,
        help_text="SHA256 checksum del archivo (opcional, para validación extra)"
    )
    
    delete_invalid = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Si es True, elimina archivos inválidos de R2 automáticamente"
    )
    
    validate_audio = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Si es True, valida que sea un archivo de audio válido"
    )
    
    metadata_updates = serializers.DictField(
        required=False,
        default=dict,
        help_text="Actualizaciones a metadata (ej: título corregido)"
    )
    
    def validate_checksum(self, value):
        """Validar formato de checksum SHA256"""
        if not value:
            return ""
        
        # SHA256 debe ser hex string de 64 caracteres
        if not re.match(r'^[a-fA-F0-9]{64}$', value):
            raise ValidationError(
                "El checksum debe ser un string hexadecimal SHA256 de 64 caracteres"
            )
        
        return value.lower()  # Normalizar a minúsculas
    
    def validate_metadata_updates(self, value):
        """Validar actualizaciones de metadata"""
        if not isinstance(value, dict):
            raise ValidationError("Las actualizaciones de metadata deben ser un objeto")
        
        # Limitar tamaño
        updates_json = json.dumps(value)
        if len(updates_json) > 5 * 1024:  # 5KB máximo
            raise ValidationError("Las actualizaciones de metadata son demasiado grandes")
        
        return value


class UploadSessionSerializer(serializers.ModelSerializer):
    """
    Serializer para sesiones de upload
    """
    
    user = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    file_in_r2 = serializers.SerializerMethodField()
    
    class Meta:
        from api2.models import UploadSession
        model = UploadSession
        fields = [
            'id',
            'user',
            'file_name',
            'file_size',
            'file_type',
            'original_file_name',
            'status',
            'status_message',
            'confirmed',
            'confirmed_at',
            'can_confirm',
            'expires_at',
            'created_at',
            'updated_at',
            'completed_at',
            'file_in_r2',
            'metadata'
        ]
        read_only_fields = fields
    
    def get_user(self, obj):
        """Obtener información básica del usuario"""
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }
    
    def get_can_confirm(self, obj):
        """Determinar si la sesión puede ser confirmada"""
        return obj.can_confirm
    
    def get_file_in_r2(self, obj):
        """Verificar si el archivo existe en R2"""
        from api2.utils.r2_direct import r2_direct
        if not obj.file_key:
            return False
        
        file_exists, _ = r2_direct.verify_file_uploaded(obj.file_key)
        return file_exists


class UploadQuotaSerializer(serializers.ModelSerializer):
    """
    Serializer para información de cuota de upload
    """
    
    class Meta:
        from api2.models import UploadQuota
        model = UploadQuota
        fields = [
            'daily_uploads_count',
            'daily_uploads_size',
            'daily_uploads_reset_at',
            'pending_uploads_count',
            'pending_uploads_size',
            'total_uploads_count',
            'total_uploads_size',
            'max_daily_uploads',
            'max_daily_size',
            'max_file_size',
            'max_total_storage',
            'updated_at'
        ]
        read_only_fields = fields
    
    def to_representation(self, instance):
        """Formatear datos para frontend"""
        data = super().to_representation(instance)
        
        # Convertir bytes a unidades legibles
        def format_bytes(bytes_value):
            if bytes_value >= 1024 * 1024 * 1024:  # GB
                return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"
            elif bytes_value >= 1024 * 1024:  # MB
                return f"{bytes_value / (1024 * 1024):.2f} MB"
            elif bytes_value >= 1024:  # KB
                return f"{bytes_value / 1024:.2f} KB"
            else:
                return f"{bytes_value} bytes"
        
        # Formatear tamaños
        data['daily_uploads_size_formatted'] = format_bytes(data['daily_uploads_size'])
        data['pending_uploads_size_formatted'] = format_bytes(data['pending_uploads_size'])
        data['total_uploads_size_formatted'] = format_bytes(data['total_uploads_size'])
        data['max_daily_size_formatted'] = format_bytes(data['max_daily_size'])
        data['max_file_size_formatted'] = format_bytes(data['max_file_size'])
        data['max_total_storage_formatted'] = format_bytes(data['max_total_storage'])
        
        # Calcular porcentajes y disponibilidad
        data['daily_usage_percent'] = min(100, int(
            (data['daily_uploads_size'] / data['max_daily_size']) * 100
        )) if data['max_daily_size'] > 0 else 0
        
        data['storage_usage_percent'] = min(100, int(
            (data['total_uploads_size'] / data['max_total_storage']) * 100
        )) if data['max_total_storage'] > 0 else 0
        
        data['daily_uploads_remaining'] = max(
            0, data['max_daily_uploads'] - data['daily_uploads_count']
        )
        
        data['daily_size_remaining'] = max(
            0, data['max_daily_size'] - data['daily_uploads_size']
        )
        
        data['daily_size_remaining_formatted'] = format_bytes(data['daily_size_remaining'])
        
        # Tiempo hasta reset
        reset_at = instance.daily_uploads_reset_at
        now = timezone.now()
        next_reset = reset_at + timedelta(days=1)
        
        if now > next_reset:
            data['next_reset_in'] = "Ya debería haberse reseteado"
            data['next_reset_seconds'] = 0
        else:
            delta = next_reset - now
            data['next_reset_in'] = str(delta).split('.')[0]  # Remover microsegundos
            data['next_reset_seconds'] = int(delta.total_seconds())
        
        return data


class BatchUploadSerializer(serializers.Serializer):
    """
    Serializer para uploads por lotes (futura implementación)
    """
    
    files = serializers.ListField(
        child=DirectUploadRequestSerializer(),
        max_length=10,  # Máximo 10 archivos por batch
        help_text="Lista de archivos para upload por lotes"
    )
    
    batch_id = serializers.CharField(
        required=False,
        max_length=50,
        help_text="ID personalizado para el batch (opcional)"
    )
    
    parallel_uploads = serializers.IntegerField(
        required=False,
        default=3,
        min_value=1,
        max_value=5,
        help_text="Número máximo de uploads paralelos"
    )
    
    def validate(self, data):
        """Validaciones cruzadas para batch"""
        files = data.get('files', [])
        
        # Verificar límite total de tamaño
        total_size = sum(file_data.get('file_size', 0) for file_data in files)
        max_batch_size = 1 * 1024 * 1024 * 1024  # 1GB por batch
        
        if total_size > max_batch_size:
            raise ValidationError(
                f"El tamaño total del batch no puede exceder {max_batch_size // (1024*1024*1024)}GB"
            )
        
        # Verificar que no haya nombres duplicados
        filenames = [f.get('file_name') for f in files if f.get('file_name')]
        if len(filenames) != len(set(filenames)):
            raise ValidationError("No se permiten nombres de archivo duplicados en un batch")
        
        return data