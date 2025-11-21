from rest_framework import serializers
from .models import Song, Like, Download, Comment, CommentReaction, MusicEvent, PlayHistory, UserProfile
from .r2_utils import generate_presigned_url
from typing import List, Dict, Any, Optional
from django.contrib.auth import get_user_model

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
import os
from rest_framework import serializers
from .models import Song
from .r2_utils import upload_file_to_r2

# api2/serializers.py - Agrega esto al final
import os
from rest_framework import serializers
from .models import Song
from .r2_utils import upload_file_to_r2

class SongUploadSerializer(serializers.Serializer):
    """Serializer para subir canciones con archivos"""
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
        """Validar archivo de audio"""
        valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac']
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato de archivo no soportado. Formatos válidos: {valid_extensions}"
            )
        # Validar tamaño (max 100MB)
        max_size = 100 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("El archivo no puede ser mayor a 100MB")
        return value

    def validate_image_file(self, value):
        """Validar archivo de imagen"""
        if value:
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
            ext = os.path.splitext(value.name)[1].lower()
            if ext not in valid_extensions:
                raise serializers.ValidationError(
                    f"Formato de imagen no soportado. Formatos válidos: {valid_extensions}"
                )
            # Validar tamaño (max 10MB)
            max_size = 10 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError("La imagen no puede ser mayor a 10MB")
        return value

    def create(self, validated_data):
        """Crear la canción y subir archivos a R2"""
        # Extraer archivos
        audio_file = validated_data.pop('audio_file')
        image_file = validated_data.pop('image_file', None)
        
        # Crear instancia de Song
        song = Song.objects.create(**validated_data)
        
        try:
            # Subir archivo de audio
            audio_key = f"songs/{song.id}/audio{os.path.splitext(audio_file.name)[1]}"
            if upload_file_to_r2(audio_file, audio_key, 'audio/mpeg'):
                song.file_key = audio_key
            else:
                song.delete()
                raise serializers.ValidationError("Error al subir el archivo de audio a R2")
            
            # Subir imagen si existe
            if image_file:
                image_key = f"songs/{song.id}/cover{os.path.splitext(image_file.name)[1]}"
                if upload_file_to_r2(image_file, image_key, 'image/jpeg'):
                    song.image_key = image_key
            
            song.save()
            return song
            
        except Exception as e:
            # Limpiar en caso de error
            if song.id:
                song.delete()
            raise serializers.ValidationError(f"Error al crear la canción: {str(e)}")