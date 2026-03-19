# api2/serializers/discovery_serializers.py
from rest_framework import serializers
from api2.models import Song
from api2.r2_utils import generate_presigned_url
from django.db.models import F

class DiscoverySongSerializer(serializers.ModelSerializer):
    """
    Serializer ultra-ligero para secciones de descubrimiento
    Solo incluye campos necesarios para rankings y listados
    """
    image_url = serializers.SerializerMethodField()
    popularity_score = serializers.SerializerMethodField()

    class Meta:
        model = Song
        fields = [
            'id', 'title', 'artist', 'genre', 'duration',
            'plays_count', 'downloads_count', 'likes_count',
            'popularity_score', 'image_url', 'created_at'
        ]

    def get_image_url(self, obj):
        """URL temporal de la imagen (expira en 1 hora)"""
        if obj.image_key:
            return generate_presigned_url(obj.image_key, expiration=3600)
        return None

    def get_popularity_score(self, obj):
        """
        Fórmula de popularidad:
        plays * 1 + downloads * 2 + likes * 3
        """
        return (obj.plays_count * 1) + (obj.downloads_count * 2) + (obj.likes_count * 3)

class GenreSerializer(serializers.Serializer):
    """Serializer para géneros con conteo de canciones"""
    name = serializers.CharField()
    song_count = serializers.IntegerField()
    sample_image = serializers.URLField(allow_null=True)
    top_artists = serializers.ListField(child=serializers.CharField())

class DiscoveryMetadataSerializer(serializers.Serializer):
    """Metadatos comunes para respuestas de descubrimiento"""
    cached = serializers.BooleanField()
    cache_ttl = serializers.IntegerField()
    total = serializers.IntegerField()
    timestamp = serializers.DateTimeField()