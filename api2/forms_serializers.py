# api2/forms_serializers.py
from rest_framework import serializers
from .models import Song, MusicEvent

class SongUploadSerializer(serializers.Serializer):
    """Serializer para el proceso de upload de canciones"""
    title = serializers.CharField(max_length=255)
    artist = serializers.CharField(max_length=255)
    genre = serializers.CharField(max_length=100)
    duration = serializers.CharField(max_length=20, required=False)
    is_public = serializers.BooleanField(default=True)
    
    # Información de archivos (no se guardan en BD, solo para validación)
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
        valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac']
        import os
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in valid_extensions:
            raise serializers.ValidationError(
                f"Formato de archivo no soportado. Formatos válidos: {valid_extensions}"
            )
        # Validar tamaño (max 50MB)
        max_size = 50 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("El archivo no puede ser mayor a 50MB")
        return value

    def validate_image_file(self, value):
        """Validar archivo de imagen"""
        if value:
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            import os
            ext = os.path.splitext(value.name)[1].lower()
            if ext not in valid_extensions:
                raise serializers.ValidationError(
                    f"Formato de imagen no soportado. Formatos válidos: {valid_extensions}"
                )
            # Validar tamaño (max 5MB)
            max_size = 5 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError("La imagen no puede ser mayor a 5MB")
        return value

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
    image_file = serializers.ImageField(required=False)