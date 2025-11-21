# api2/forms_serializers.py
from rest_framework import serializers
from .models import Song, MusicEvent

# api2/serializers.py (parte para upload)
from rest_framework import serializers
import os
from .r2_utils import upload_file_to_r2, generate_presigned_url

class SongUploadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    artist = serializers.CharField(max_length=255)
    genre = serializers.CharField(max_length=100)
    audio_file = serializers.FileField()
    image_file = serializers.ImageField(required=False)
    
    def validate_audio_file(self, value):
        """Validar archivo de audio"""
        valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac']
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato no soportado. Use: {', '.join(valid_extensions)}"
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
                    f"Formato de imagen no soportado. Use: {', '.join(valid_extensions)}"
                )
            
            # Validar tamaño (max 10MB)
            max_size = 10 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError("La imagen no puede ser mayor a 10MB")
        
        return value

    def create(self, validated_data):
        from .models import Song
        
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
                raise serializers.ValidationError("Error al subir el archivo de audio")
            
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

class EventCreateSerializer(serializers.Serializer):
    """Serializer para crear eventos con upload de imagen"""
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    event_type = serializers.ChoiceField(choices=[
        ('concert', 'Concierto'),
        ('festival', 'Festival'),
        ('party', 'Fiesta'),
        ('workshop', 'Taller'),
        ('other', 'Otro'),
    ])
    event_date = serializers.DateTimeField()
    location = serializers.CharField(max_length=255)
    venue = serializers.CharField(max_length=255, required=False)
    ticket_url = serializers.URLField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_active = serializers.BooleanField(default=True)
    is_featured = serializers.BooleanField(default=False)
    image_file = serializers.ImageField(required=False)  # ⬅️ Coma eliminada