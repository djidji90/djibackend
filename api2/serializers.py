from rest_framework import serializers
from .models import Song, Like, Download, Comment, CommentReaction, MusicEvent, PlayHistory, UserProfile
from .r2_utils import generate_presigned_url
from typing import List, Dict, Any, Optional
from django.contrib.auth import get_user_model
from .r2_utils import upload_file_to_r2, delete_file_from_r2, generate_presigned_url
import os
import uuid
from django.db import transaction

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

    def get_is_user_comment(self, obj) -> bool:
        """Verificar si el comentario es del usuario actual"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return obj.user == request.user
        return False

    def get_reactions_count(self, obj) -> Dict[str, int]:
        """Contar reacciones por tipo"""
        from django.db.models import Count
        reactions = obj.reactions.values('reaction_type').annotate(count=Count('id'))
        return {r['reaction_type']: r['count'] for r in reactions}

    def get_user_reaction(self, obj) -> Optional[str]:
        """Obtener la reacción del usuario actual"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                reaction = obj.reactions.get(user=request.user)
                return reaction.reaction_type
            except CommentReaction.DoesNotExist:
                return None
        return None

    def validate_content(self, value):
        """Validar contenido del comentario"""
        if len(value.strip()) == 0:
            raise serializers.ValidationError("El comentario no puede estar vacío.")
        if len(value) > 1000:
            raise serializers.ValidationError("El comentario no puede tener más de 1000 caracteres.")
        return value


class CommentReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    comment = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CommentReaction
        fields = ['id', 'comment', 'user', 'reaction_type', 'created_at']
        read_only_fields = ['created_at']

    def validate_reaction_type(self, value):
        """Validar tipo de reacción"""
        valid_reactions = ['like', 'love', 'laugh', 'sad', 'angry']
        if value not in valid_reactions:
            raise serializers.ValidationError(f"Tipo de reacción inválido. Válidos: {valid_reactions}")
        return value


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