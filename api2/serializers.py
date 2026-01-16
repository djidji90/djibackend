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

class SongUploadSerializer(serializers.Serializer):
    """Serializer optimizado para subir canciones"""
    title = serializers.CharField(max_length=255)
    artist = serializers.CharField(max_length=255)
    genre = serializers.CharField(max_length=100)
    duration = serializers.CharField(max_length=20, required=False, allow_blank=True)
    is_public = serializers.BooleanField(default=True)
    
    # Campos de archivo
    audio_file = serializers.FileField(
        max_length=500,
        allow_empty_file=False,
        help_text="Archivo de audio (MP3, WAV, etc.)"
    )
    image_file = serializers.ImageField(
        max_length=500,
        required=False,
        allow_empty_file=True,
        help_text="Imagen de portada (JPG, PNG, etc.)"
    )

    def validate_audio_file(self, value):
        """Validación optimizada por performance"""
        # 1. Chequear tamaño primero (más rápido)
        max_size = 100 * 1024 * 1024  # 100MB
        if value.size > max_size:
            raise serializers.ValidationError("El archivo no puede ser mayor a 100MB")
        
        # 2. Chequear extensión con set para O(1)
        valid_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.webm'}
        ext = os.path.splitext(value.name)[1].lower()
        
        if ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato no soportado. Usa: MP3, WAV, OGG, M4A, FLAC, AAC, WEBM"
            )
        
        # 3. Chequear MIME type si está disponible
        if hasattr(value, 'content_type'):
            audio_mimes = {
                'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/flac',
                'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/webm'
            }
            if value.content_type not in audio_mimes:
                raise serializers.ValidationError("Tipo de archivo no válido")
        
        return value

    def validate_image_file(self, value):
        """Validación optimizada para imágenes"""
        if not value:
            return value
        
        # 1. Chequear tamaño primero
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("La imagen no puede ser mayor a 10MB")
        
        # 2. Chequear extensión
        valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        ext = os.path.splitext(value.name)[1].lower()
        
        if ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato de imagen no soportado. Usa: JPG, PNG, WEBP, GIF"
            )
        
        return value

    def create(self, validated_data):
        """
        Creación atómica optimizada:
        1. Sube archivos a R2
        2. Si todo OK, crea registro en BD
        3. Si hay error, limpia todo
        """
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError("Usuario no autenticado")
        
        # Extraer archivos
        audio_file = validated_data.pop('audio_file')
        image_file = validated_data.pop('image_file', None)
        
        # Generar keys únicas ANTES de subir
        unique_id = uuid.uuid4().hex[:12]
        audio_key = f"songs/{unique_id}_audio{os.path.splitext(audio_file.name)[1].lower()}"
        image_key = None
        
        if image_file:
            image_key = f"images/{unique_id}_cover{os.path.splitext(image_file.name)[1].lower()}"
        
        uploaded_files = []  # Para limpieza en caso de error
        
        try:
            # Transacción atómica
            with transaction.atomic():
                # 1. Subir audio a R2
                audio_content_type = getattr(audio_file, 'content_type', None)
                if not upload_file_to_r2(audio_file, audio_key, content_type=audio_content_type):
                    raise serializers.ValidationError("Error al subir archivo de audio")
                uploaded_files.append(('audio', audio_key))
                
                # 2. Subir imagen si existe
                if image_file and image_key:
                    image_content_type = getattr(image_file, 'content_type', None)
                    if not upload_file_to_r2(image_file, image_key, content_type=image_content_type):
                        # Limpiar audio si falla imagen
                        delete_file_from_r2(audio_key)
                        raise serializers.ValidationError("Error al subir imagen")
                    uploaded_files.append(('image', image_key))
                
                # 3. Crear canción en BD CON TODOS los datos
                song = Song.objects.create(
                    **validated_data,
                    file_key=audio_key,
                    image_key=image_key,
                    uploaded_by=request.user  # ← Asignado aquí, no después
                )
                
                return song
                
        except Exception as e:
            # 4. LIMPIEZA EN CASO DE ERROR
            for file_type, file_key in uploaded_files:
                try:
                    delete_file_from_r2(file_key)
                except Exception:
                    pass  # Loggear en producción
            
            # Re-lanzar error apropiado
            if isinstance(e, serializers.ValidationError):
                raise e
            raise serializers.ValidationError(f"Error al crear la canción: {str(e)}")

# api2/serializers.py - Agregar al final del archivo

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